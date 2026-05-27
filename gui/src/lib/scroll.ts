/** Auto-scroll if the viewport is within 40px of the bottom. */
export function shouldAutoScroll(m: {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}): boolean {
  return m.scrollHeight - (m.scrollTop + m.clientHeight) < 40;
}
