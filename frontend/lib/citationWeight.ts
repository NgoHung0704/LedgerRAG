export type CitationWeight = "strong" | "normal" | "weak";

/** How far above the weakest source a citation must sit to be emphasised, and
 *  how close to it before it is faded — as a share of the spread between the
 *  best and worst source of THIS answer. */
const STRONG_AT = 0.66;
const WEAK_AT = 0.33;

/** Below this much spread, relative to the best score, the sources are treated
 *  as equally relevant and none is marked. A cross-encoder that scores eight
 *  passages 0.81, 0.80, 0.80, 0.79 is saying they are the same; stretching that
 *  into a hierarchy would show the reader a distinction the data does not make,
 *  which is worse than showing none. */
const FLAT_ENOUGH = 0.1;

/** Which sources the answer actually leans on, from their retrieval scores.
 *
 *  Read as a position within the spread of THIS answer's scores, not as a ratio
 *  to the best one. Two reasons, both measured rather than assumed:
 *
 *  - the scale is not ours to know. With the reranker enabled these are
 *    cross-encoder relevance scores; with it disabled they are RRF fusion
 *    scores two orders of magnitude smaller. A position within the observed
 *    range means the same thing in both.
 *  - a ratio to the best barely fires. Cross-encoder scores cluster — 0.92,
 *    0.88, 0.81, 0.74 — so "less than half the best" almost never happens, and
 *    the dimming that was supposed to guide the eye never appeared.
 */
export function citationWeights(scores: number[]): CitationWeight[] {
  const flat: CitationWeight[] = scores.map(() => "normal");
  if (scores.length < 2) return flat;

  const best = Math.max(...scores);
  const worst = Math.min(...scores);
  const spread = best - worst;
  if (best <= 0 || spread <= best * FLAT_ENOUGH) return flat;

  return scores.map((score) => {
    const position = (score - worst) / spread;
    if (position >= STRONG_AT) return "strong";
    if (position <= WEAK_AT) return "weak";
    return "normal";
  });
}
