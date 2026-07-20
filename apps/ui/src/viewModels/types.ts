/**
 * ViewModel types for decision-backed UI surfaces.
 *
 * Flow: API DTO (`types/decisions.ts`) -> ViewModel builder -> component.
 * Components render ViewModels; they do not decide diagnostic meaning.
 */

import type { DecisionStatus } from "@zigbeelens/shared";

export type DecisionPillTone =
  | "neutral"
  | "info"
  | "watch"
  | "action"
  | "coverage"
  | "muted";

export interface DecisionStatusPillViewModel {
  status: DecisionStatus;
  label: string;
  tone: DecisionPillTone;
  compactLabel?: string;
}

export interface DecisionReasonViewModel {
  code: string;
  text: string;
}

export interface DecisionLimitationViewModel {
  code: string;
  text: string;
}

export interface DecisionSuggestedCheckViewModel {
  code: string;
  text: string;
}

export interface DecisionRowViewModel {
  id: string;
  primary: string;
  secondary?: string;
  meta?: string;
}

export interface DecisionSectionViewModel {
  title: string;
  items: DecisionRowViewModel[];
}

export interface DecisionViewModel {
  subjectType: string;
  subjectId: string;
  statusPill: DecisionStatusPillViewModel;
  leadText?: string;
  reasons: DecisionReasonViewModel[];
  limitations: DecisionLimitationViewModel[];
  suggestedChecks: DecisionSuggestedCheckViewModel[];
  coverageLabels: string[];
  evidenceDetails?: DecisionRowViewModel[];
}
