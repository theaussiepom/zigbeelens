/**
 * Compatibility export — prefer DeviceSnapshotHistory on Device Detail.
 * Snapshot history is no longer mounted inside NodeDrawer.
 */
export {
  DeviceSnapshotHistory as SnapshotHistorySection,
  DeviceSnapshotHistory,
  SnapshotHistoryContent,
} from "@/components/meshGraph/DeviceSnapshotHistory";
