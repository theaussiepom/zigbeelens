/** Shared API response helpers used across domain fetch modules. */

export interface Paginated<T> {
  items: T[];
  total: number;
}
