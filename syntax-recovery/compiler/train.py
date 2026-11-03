"""Train the Isolation Forest recovery model:  python -m compiler.train"""
from .corpus import generate_programs, load_hand_written, split_corpus, token_types
from .model import IsolationForestModel, save_model, abstract, MODEL_PATH, EXTRA_VOCAB
from .grammar import load_grammar

GEN_COUNT = 4000
GEN_SEED = 7
SPLIT_SEED = 11
HAND_WEIGHT = 10


def build_splits():
    generated = generate_programs(GEN_COUNT, seed=GEN_SEED)
    hand = load_hand_written()
    return split_corpus(generated, hand, seed=SPLIT_SEED)


def main():
    train, dev, test = build_splits()
    g = load_grammar()
    vocab = {abstract(t) for t in g.terminals} | set(EXTRA_VOCAB)
    hand = set(load_hand_written())
    # Oversample hand-written programs so their token windows carry more weight.
    seqs = []
    for p in train:
        seq = [abstract(t) for t in token_types(p)]
        seqs.extend([seq] * (HAND_WEIGHT if p in hand else 1))
    meta = {"generated_programs": GEN_COUNT, "hand_written_programs": len(load_hand_written()),
            "train_programs": len(train), "dev_programs": len(dev), "test_programs": len(test),
            "gen_seed": GEN_SEED, "split_seed": SPLIT_SEED, "hand_weight": HAND_WEIGHT}
    model = IsolationForestModel.train(seqs, vocab, meta)
    save_model(model)
    summary = model.summary()
    print(f"trained Isolation Forest on {len(train)} programs "
          f"({summary['training_windows']} token windows, {summary['features']} features) "
          f"-> {MODEL_PATH}")


if __name__ == "__main__":
    main()
