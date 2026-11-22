# Keyword ranking comparison

The project uses **BM25** inside [`keyword_rank`](../app/retrieval.py) to rank past successful questions. It replaces the previous capped, IDF-weighted overlap scorer. The function name and `RETRIEVAL_MODE=keyword` setting remain the same.

TF-IDF has several variations. This comparison uses TF-IDF-weighted query and document vectors ranked by cosine similarity. Our BM25 formulation scores each distinct query term once, without a separate query-frequency factor.

Here, the query is the current question plus the last two successful question texts from the current session. Each document is one candidate past question, drawn from up to 200 recent successful queries for the same database. Historical SQL is attached after selection; it is not scored or embedded. The full schema is supplied separately.

Tokenization lowercases ASCII words and numbers, drops one-character words, and removes at most one final `s` from words longer than two characters unless they end in `ss`. This preserves terms such as `class` and avoids empty tokens, but remains a simple heuristic rather than linguistic stemming.

| Behavior | Previous overlap scorer | TF-IDF with cosine similarity | Current BM25 scorer |
| --- | --- | --- | --- |
| Word rarity | IDF gives rarer words more weight | IDF gives rarer words more weight | IDF gives rarer words more weight |
| Repeated word in a past question | Capped at the word's count in the query | Raises TF weight; cosine normalization moderates its effect on similarity | Raises the term's contribution, with diminishing returns when document length is held fixed |
| Repeated word in the query | Can increase credit through `min(query_count, document_count)` | Changes the query's TF weights, depending on the TF variant; cosine normalization also affects the resulting similarity | No extra weight in the formulation described here |
| Question length | No length adjustment | Normalizes vector magnitude, rather than directly using the number of words | Explicitly adjusts for document length relative to the corpus average |
| Word order | Ignored | Ignored | Ignored |

## BM25 formula

For candidate question $d$ and search query $q$:

$$
\operatorname{score}(d,q) =
\sum_{t \in \operatorname{unique}(q)}
\ln\left(1 + \frac{N - df(t) + 0.5}{df(t) + 0.5}\right)
\cdot
\frac{f(t,d)(k_1 + 1)}
{f(t,d) + k_1\left(1 - b + b\frac{|d|}{\operatorname{avgdl}}\right)}
$$

| Symbol | Meaning in this project |
| --- | --- |
| $t$ | One distinct normalized query word |
| $N$ | Number of candidate past questions |
| $df(t)$ | Number of candidate questions containing the word |
| $f(t,d)$ | Number of occurrences of the word in this candidate question |
| $\lvert d\rvert$ | Candidate question length in normalized tokens, including repetitions |
| $\operatorname{avgdl}$ | Mean token length across all candidates, including empty documents |
| $k_1 = 1.2$ | Controls diminishing returns from repeated document words |
| $b = 0.75$ | Controls document-length normalization |

These parameter defaults and the positive IDF expression follow [Lucene's BM25 reference](https://lucene.apache.org/core/9_12_3/core/org/apache/lucene/search/similarities/BM25Similarity.html). The positive IDF keeps terms useful even if they appear in every candidate. Query words absent from the corpus contribute nothing. Repeating a word in the query does not increase its weight.

For example, searching for `customers` ranks `customers` above `customers with recent orders` because both match once and the first question is shorter. For equal-length documents, additional occurrences of a matching term increase its contribution with diminishing returns.

Only positive-score candidates enter the keyword ranking, with input order breaking exact ties. Empty queries, empty candidate lists, and entirely tokenless candidates return no keyword matches.

## Hybrid retrieval

BM25 and Qdrant cosine search each rank the current historical candidates. Qdrant persists question embeddings and reuses them across searches; only the query and missing historical question texts need embedding. Reciprocal rank fusion adds `1 / (60 + rank)` from each ranking, with equal weight and one-based ranks, then selects up to three examples. A candidate with no BM25 match can still enter through semantic search. Explicit keyword mode, embedding failures, and vector-storage failures use BM25 alone. See [vector storage](vector-storage.md) for isolation and persistence details.

All three lexical approaches in the table rely on shared tokens and ignore word order. Semantic search helps match differently worded questions. This change has offline regression coverage; the published SQL benchmark starts each case with empty history and therefore does not measure retrieval quality.
