# Second question: history format x model — frozen record

scenario_rescue.yaml v1.2 / swapped run extracted with codebook_v1.yaml v3.3 (earlier run: v2.1)

In the earlier q2, only gemini received the history folded into the message (quoted as 「【あなたの回答】」, "your answer"), while the other three received native turns. We swapped the formats and ran again.

| Subject | Earlier | Swapped |
|---|---|---|
| gemini | folded | native turns |
| openai | native turns | folded |
| anthropic | native turns | folded |
| qwen | native turns | folded |

4 orders x 10 trials x 3 turns each. Extraction by the two models other than the subject (fully crossed); only two-coder agreement counts.

## 1. Order lock-in — the three patterns survive swapping the format

North counts, first question -> second question. Earlier: RESULTS_q2.md section 1 (3-coder unanimity); swapped: 2-coder agreement. (u n) is the number of cases where the two coders split or only one value was obtained.

| Subject | Format | KA-KD | KD-KA | NA-ND | ND-NA |
|---|---|---|---|---|---|
| gemini earlier | folded | 8->10 | 10->10 | 0->9 | 10->0 |
| gemini swapped | native turns | 8->10 | 10->10 | 0->7 | 10->0 |
| openai earlier | native turns | 0->0 | 10->10 | 0->0 | 0->0 |
| openai swapped | folded | 0(u1)->0 | 10->10 | 0(u1)->0 | 0->0 |
| anthropic earlier | native turns | 0->9 | 10->10 | 0->0 | 0->0 |
| anthropic swapped | folded | 0->8(u1) | 9->7(u1) | 0->0 | 0->0 |
| qwen earlier | native turns | 7->10 | 10->10 | 0->7 | 7->1 |
| qwen swapped | folded | 10->10 | 10->10 | 0->7 | 10->0 |

## 2. Citing and denying the attribute — KD turns

| Subject | Position | frame_cited true | frame_denied true |
|---|---|---|---|
| gemini | t2 | 9/10 (1 split) | 1/10 (0 split) |
| gemini | t1 | 8/10 (1 split) | 0/10 (0 split) |
| openai | t2 | 0/10 (0 split) | 10/10 (0 split) |
| openai | t1 | 0/10 (0 split) | 10/10 (0 split) |
| anthropic | t2 | 10/10 (0 split) | 5/10 (3 split) |
| anthropic | t1 | 2/10 (0 split) | 9/10 (0 split) |
| qwen | t2 | 7/10 (0 split) | 3/10 (2 split) |
| qwen | t1 | 6/10 (0 split) | 2/10 (0 split) |

## 3. Consistency turn — the ordering does not change when the format is swapped

Earlier: 3-coder unanimity; swapped: 2-coder agreement. The agreement rules differ in strictness, so split counts are not compared directly.

| Subject | Format | Consistent | Partly consistent | Inconsistent | Split |
|---|---|---|---|---|---|
| gemini earlier | folded | 38/40 | 2 | 0 | 0 |
| gemini swapped | native turns | 39/40 | 0 | 1 | 0 |
| openai earlier | native turns | 40/40 | 0 | 0 | 0 |
| openai swapped | folded | 40/40 | 0 | 0 | 0 |
| anthropic earlier | native turns | 10/40 | 19 | 6 | 5 |
| anthropic swapped | folded | 8/40 | 21 | 2 | 9 |
| qwen earlier | native turns | 30/40 | 4 | 2 | 4 |
| qwen swapped | folded | 26/40 | 8 | 4 | 2 |

**Agreement (compared within the same coder pair)**

| Subject | Coders | Earlier AC1 | Swapped AC1 |
|---|---|---|---|
| gemini | anthropic + openai | 1.00 | 1.00 |
| openai | anthropic + qwen | 1.00 | 1.00 |
| anthropic | gemini + qwen | 0.84 | 0.73 |
| qwen | gemini + openai | 0.89 | 0.94 |

**Cell differences (by order, swapped run)**

C = consistent, P = partly consistent, I = inconsistent, S = the two coders split, U = undeterminable

| Subject | KA-KD | KD-KA | NA-ND | ND-NA |
|---|---|---|---|---|
| anthropic | P5 S2 C2 I1 | P6 S3 I1 | P5 S3 C2 | P5 C4 S1 |
| qwen | P7 C3 | C10 | C6 I3 P1 | C7 S2 I1 |

### 3b. Comparison at the same codebook version (earlier format also v3.3, same coder pairs)

anthropic and qwen in the earlier format were re-extracted with v3.3 by the same coder pairs as the swapped run (anthropic <- gemini + qwen, qwen <- gemini + openai). Two-coder agreement only.

| Subject | Format | Total | KA-KD | KD-KA | NA-ND | ND-NA |
|---|---|---|---|---|---|---|
| anthropic earlier | native turns | P19 C11 I6 S4 | I6 P3 S1 | P8 C1 S1 | P4 C4 S2 | C6 P4 |
| anthropic swapped | folded | P21 S9 C8 I2 | P5 S2 C2 I1 | P6 S3 I1 | P5 S3 C2 | P5 C4 S1 |
| qwen earlier | native turns | C30 P4 S3 I3 | C6 P2 S2 | C8 P2 | C8 I1 S1 | C8 I2 |
| qwen swapped | folded | C26 P8 I4 S2 | P7 C3 | C10 | C6 I3 P1 | C7 S2 I1 |

**No difference due to codebook version was seen.** Re-counting the earlier format under v3.3, anthropic KA-KD stays at "inconsistent" 6/10 (6 under v2.1 as well), and the overall distribution is nearly the same as under v2.1. The earlier-swapped difference is not the codebook version.

**The remaining difference is either format or run-to-run variation.** The swapped run also re-sampled the subject responses, so a format effect overlaps with the variation from rerunning the same condition. Both cells that differed are 10 vs 10 and do not reach significance in a two-sided exact test.

| Cell | Earlier (native turns) | Swapped (folded) | Fisher p |
|---|---|---|---|
| anthropic KA-KD "inconsistent" | 6/10 | 1/10 | 0.057 |
| qwen KA-KD "partly consistent" | 2/10 | 7/10 | 0.070 |

Before the rerun, these two cells suggested the hypothesis that "under the folded format both models shift toward partly consistent". **This hypothesis was not supported under the prespecified rule in 3c** (kept for the record).


### 3c. Rerun verdict (rule fixed in ANALYSIS_PLANS before seeing the data)

Design `q2_rerun`: anthropic and qwen KA-KD rerun with native turns, 20 trials each (2026-11-16, text character-identical to q2). Extraction v3.3, same coder pairs as 3b, two-coder agreement only. Extraction failures: 0.

| Subject | Target cell | Earlier native (11-05) | Rerun native (11-16) | Folded (11-16) | Primary p | Stability p | Verdict |
|---|---|---|---|---|---|---|---|
| anthropic | "inconsistent" | 6/10 | 8/20 | 1/10 | 0.060 | 0.442 | not supported |
| qwen | "partly consistent" | 2/10 | 7/20 | 7/10 | 0.059 | 0.675 | not supported |

**Under the prespecified rule, the two designated cells did not meet the criterion supporting a format effect.** We do not claim that "both models shift toward partly consistent under the folded format". The stability check did not detect a between-run difference for the prespecified categories (this does not mean the whole distribution was stable; see the exploratory table below).

**Exploratory findings (outside the rule; not confirmatory)**

| Subject | Value | Earlier native (11-05) | Rerun native (11-16) | Folded (11-16) | p, native vs native | p, same-day native vs folded |
|---|---|---|---|---|---|---|
| anthropic | consistent | 0/10 | 2/20 | 2/10 | 0.540 | 0.584 |
| anthropic | partly consistent | 3/10 | 9/20 | 5/10 | 0.694 | 1.000 |
| anthropic | inconsistent | 6/10 | 8/20 | 1/10 | 0.442 | 0.204 |
| qwen | consistent | 6/10 | 2/20 | 3/10 | 0.007 | 0.300 |
| qwen | partly consistent | 2/10 | 7/20 | 7/10 | 0.675 | 0.122 |
| qwen | inconsistent | 0/10 | 9/20 | 0/10 | 0.013 | 0.013 |

Exploratorily, qwen's output distribution also differed between run dates within the same format (non-designated categories). Testing a format difference therefore needs a design that interleaves both formats within the same run period. The table above lists 12 uncorrected tests as exploratory material and is not used for confirmation.

## 4. Extraction quality

- `choice`: agreement 0.994, AC1 0.99 over 318 turns with both coders. In each of the 2 splits, one coder returned "undeterminable"
- Extractions that returned no JSON: 2 (qwen on openai KA-KD #2 1:decision/KA; qwen on openai NA-ND #6 1:decision/NA). These turns have only one coder value and appear as (u) in the tables
- Codebook versions: consistency, earlier {'2.1': 480} / swapped {'3.3': 320}

## 5. What can and cannot be said

**What can be said**

1. **openai's full lock-in occurs without native turns.** Its past answer quoted in the message as 「【あなたの回答】」 ("your answer") is enough to lock in both directions. The conversational role structure is not necessary; text presented as its own suffices.
2. **gemini's lack of lock-in is not due to the folded format.** With native turns it still reverses according to the attributes: NA->ND (north 0->7), ND->NA (north 10->0).
3. **gemini and openai "consistent" stays near ceiling** (swapped: gemini 39/40, openai 40/40). The ordering between models is preserved.
4. **The pattern of citing and denying the attribute is preserved.** openai on KD turns, regardless of position, cites 0/10 and denies 10/10.

**What cannot be said yet**

- The strength of anthropic's KD-KA lock (earlier 10/10 -> swapped 7/10, 1 unresolved). The direction is the same, but with 10 trials we cannot tell whether it differs
- Whether small consistency cell differences are format effects. The codebook version was ruled out in 3b, and the rerun (3c) did not support it under the prespecified rule. qwen's distribution moved across days even within the same format, so checking it would require interleaving both formats on the same day with equal trial counts
