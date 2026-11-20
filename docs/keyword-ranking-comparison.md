# Keyword ranking comparison

The project currently uses [`keyword_rank`](../app/retrieval.py) to rank past successful questions by IDF-weighted word overlap. TF-IDF and BM25 are alternatives for this keyword component of hybrid retrieval.

TF-IDF has several variations. This comparison uses TF-IDF-weighted query and document vectors ranked by cosine similarity. For BM25, it assumes a common formulation that scores each distinct query term once, without a separate query-frequency factor; other formulations can account for repeated query terms.

Here, the query is the search text, and each document is one candidate past question.

Tokenization lowercases ASCII words and numbers, drops one-character words, and removes at most one final `s` from words longer than two characters unless they end in `ss`. This preserves terms such as `class` and avoids empty tokens, but remains a simple heuristic rather than linguistic stemming.

| Behavior | Current `keyword_rank` | TF-IDF with cosine similarity | BM25 |
| --- | --- | --- | --- |
| Word rarity | IDF gives rarer words more weight | IDF gives rarer words more weight | IDF gives rarer words more weight |
| Repeated word in a past question | Capped at the word's count in the query | Raises TF weight; cosine normalization moderates its effect on similarity | Raises the term's contribution, with diminishing returns when document length is held fixed |
| Repeated word in the query | Can increase credit through `min(query_count, document_count)` | Changes the query's TF weights, depending on the TF variant; cosine normalization also affects the resulting similarity | No extra weight in the formulation described here |
| Question length | No length adjustment | Normalizes vector magnitude, rather than directly using the number of words | Explicitly adjusts for document length relative to the corpus average |
| Word order | Ignored | Ignored | Ignored |

The current scorer sums capped word overlap weighted by IDF; it does not compare TF-IDF vectors. All three approaches rely on shared tokens. The semantic search component handles similarity between differently worded questions, and reciprocal rank fusion combines the keyword and semantic rankings.
