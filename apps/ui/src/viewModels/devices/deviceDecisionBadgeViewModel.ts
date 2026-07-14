/**
 * Device inventory decision badge ViewModel (Phase 5B-1).
 *
 * Maps compact Device Story projections through shared decision copy helpers.
 * Components render this; they do not decide status meaning.
 */

import type { DeviceDecisionBadge } from "@zigbeelens/shared";
import {
  coverageLabel,
  decisionStatusCompactLabel,
  decisionStatusLabel,
  decisionStatusTone,
  headlineText,
} from "@/viewModels/decisionCopy";
import type { DecisionPillTone } from "@/viewModels/types";

export interface DeviceDecisionBadgeViewModel {
  statusLabel: string;
  compactLabel: string;
  tone: DecisionPillTone;
  headline: string;
  coverageLabels: string[];
}

export function buildDeviceDecisionBadgeViewModel(
  badge: DeviceDecisionBadge,
): DeviceDecisionBadgeViewModel {
  return {
    statusLabel: decisionStatusLabel(badge.status),
    compactLabel: decisionStatusCompactLabel(badge.status),
    tone: decisionStatusTone(badge.status),
    headline: headlineText(badge.headline_code),
    coverageLabels: badge.coverage_label_codes.map((code) => coverageLabel(code)),
  };
}
