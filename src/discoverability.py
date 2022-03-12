#!/usr/bin/python3
"""
discoverability.py term...
Search for some terms in the manual page cache.

Author: Gabriel Peery
Date: 3/12/2022
"""
import argparse
import bz2
import json
import numpy as np
import os
import pickle
from scipy.sparse import save_npz, load_npz
from sklearn.feature_extraction.text import TfidfVectorizer


def search_cosine(tfidf, query, count, vectorizer, corpus):
    input_vector = vectorizer.transform([query])
    scores = (tfidf @ input_vector.T).toarray().T[0]
    top_indices = np.argsort(scores)[-1:-count:-1]
    return list(map(lambda x : x[0], (corpus[idx] for idx in top_indices)))


def post_process_search(query, results):
    match_count = 0
    for result_idx in range(len(results)):
        real_result = results[result_idx]
        result = real_result.split()[0]
        if query in result:
            if query == result:
                # Case it is identical
                results.pop(result_idx)
                results.insert(0, real_result)
            else:
                # Case it is merely part of name
                results.pop(result_idx)
                results.insert(match_count, real_result)
            match_count += 1
    return results


def full_search(tfidf, query, count, vectorizer, corpus):
    return post_process_search(
        query,
        search_cosine(tfidf, query, count, vectorizer, corpus)
    )


def main():
    # Deal with command line arguments
    parser = argparse.ArgumentParser(description="Search for terms in "
            "the manual page cache")
    parser.add_argument("terms", type=str, nargs="+", help="terms to search")
    args = parser.parse_args()

    # Retrieve model (tfidf)
    cache_dir = os.path.join(
        os.path.dirname(os.path.realpath(os.path.abspath(__file__))),
        os.path.pardir,
        "cache"
    )
    matrix_path = os.path.join(cache_dir, ".matrix")
    corpus_path = os.path.join(cache_dir, ".corpus")
    vectorizer_path = os.path.join(cache_dir, ".vectorizer")
    cache_path = os.path.join(cache_dir, "discoverability_cache")
    if not (
        os.path.exists(matrix_path)
        and os.path.exists(corpus_path)
        and os.path.exists(vectorizer_path)
    ):
        # Need to create
        if os.path.exists(cache_path):
            # All good to create - cache exists
            with bz2.open(cache_path) as cache_file:
                corpus_dict = json.load(cache_file)
                # Just a quick tfidf model creation; format first
                corpus_dict = {
                    name : " ".join(
                        text for text in elements["sections"].values()
                    ) for name, elements in corpus_dict.items()
                }
                corpus = [(name, text) for name, text in corpus_dict.items()]
                vectorizer = TfidfVectorizer(decode_error="replace")
                tfidf = vectorizer.fit_transform(map(lambda x : x[1], corpus))
                # Save
                with open(matrix_path, "wb") as matrix_file:
                    save_npz(matrix_file, tfidf)
                with open(corpus_path, "wb") as corpus_file:
                    pickle.dump(corpus, corpus_file)
                with open(vectorizer_path, "wb") as vectorizer_file:
                    pickle.dump(vectorizer, vectorizer_file)
                # Free some memory
                del corpus_dict
        else:
            raise FileNotFoundError(f"Could not find cache at {cache_path}")
    else:
        # Grab it from before
        with open(matrix_path, "rb") as matrix_file:
            tfidf = load_npz(matrix_file)
        with open(corpus_path, "rb") as corpus_file:
            corpus = pickle.load(corpus_file)
        with open(vectorizer_path, "rb") as vectorizer_file:
            vectorizer = pickle.load(vectorizer_file)

    # Retrieve information
    query = ' '.join(args.terms)
    for result in full_search(tfidf, query, 20, vectorizer, corpus):
        print(result)


if __name__ == "__main__":
    main()

