/**
 * Architecture guard: UI contract dependency roots stay pure TypeScript/Vitest.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const FORBIDDEN_MODULES = new Set([
  "node:child_process",
  "child_process",
  "node:worker_threads",
  "worker_threads",
]);

const FORBIDDEN_CALLEES = new Set([
  "spawn",
  "spawnSync",
  "exec",
  "execFile",
  "execSync",
  "execFileSync",
  "fork",
]);

const FORBIDDEN_IDENTIFIERS = new Set(["python", "python3"]);

function listTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...listTsFiles(full));
      continue;
    }
    if (name.endsWith(".ts") || name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

function importedModule(node: ts.Node): string | null {
  if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
    return node.moduleSpecifier.text;
  }
  if (
    ts.isCallExpression(node) &&
    node.expression.kind === ts.SyntaxKind.ImportKeyword &&
    node.arguments.length === 1 &&
    ts.isStringLiteral(node.arguments[0]!)
  ) {
    return node.arguments[0]!.text;
  }
  if (
    ts.isCallExpression(node) &&
    ts.isIdentifier(node.expression) &&
    node.expression.text === "require" &&
    node.arguments.length === 1 &&
    ts.isStringLiteral(node.arguments[0]!)
  ) {
    return node.arguments[0]!.text;
  }
  return null;
}

function calleeName(expr: ts.Expression): string | null {
  if (ts.isIdentifier(expr)) return expr.text;
  if (ts.isPropertyAccessExpression(expr) && ts.isIdentifier(expr.name)) {
    return expr.name.text;
  }
  return null;
}

describe("UI contracts stay Python-free", () => {
  it("scans contract roots for child_process / python generator imports", () => {
    const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
    const roots = [
      path.join(repoRoot, "apps/ui/src/test/contracts"),
      path.join(repoRoot, "apps/ui/src/components/meshGraph/meshReportSourceContract.test.ts"),
    ];
    const files: string[] = [];
    for (const root of roots) {
      if (statSync(root).isDirectory()) files.push(...listTsFiles(root));
      else files.push(root);
    }
    expect(files.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const file of files) {
      const rel = path.relative(repoRoot, file);
      const text = readFileSync(file, "utf8");
      const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
      const visit = (node: ts.Node) => {
        const mod = importedModule(node);
        if (mod && FORBIDDEN_MODULES.has(mod)) {
          violations.push(`${rel}: imports ${mod}`);
        }
        if (mod && /generate_oracle_mock_fixtures/.test(mod)) {
          violations.push(`${rel}: imports Core fixture generator (${mod})`);
        }
        if (ts.isCallExpression(node)) {
          const name = calleeName(node.expression);
          if (name && FORBIDDEN_CALLEES.has(name)) {
            violations.push(`${rel}: calls ${name}()`);
          }
        }
        if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
          // Ignore ordinary product copy; only flag executable interpreter paths.
          if (/\/(?:bin\/)?python(?:3)?(?:\s|$)/i.test(node.text)) {
            violations.push(`${rel}: python interpreter path literal ${JSON.stringify(node.text)}`);
          }
        }
        if (ts.isIdentifier(node) && FORBIDDEN_IDENTIFIERS.has(node.text)) {
          // Allow mentioning in comments via identifiers only when used as values.
          const parent = node.parent;
          if (ts.isPropertyAccessExpression(parent) || ts.isCallExpression(parent)) {
            violations.push(`${rel}: identifier ${node.text}`);
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }

    expect(violations, violations.join("\n")).toEqual([]);
  });
});
