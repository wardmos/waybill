export function shouldRetry(attempt: number, limit: number): boolean {
  return attempt < limit;
}
