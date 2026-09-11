/** Envelope returned by the paged list endpoints. `total` counts every matching row. */
export interface Page<T> {
  total: number;
  items: T[];
}
