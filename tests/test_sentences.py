from app.sentences import SentenceSplitter


def split(*chunks):
    splitter = SentenceSplitter()
    out = []
    for chunk in chunks:
        out += splitter.feed(chunk)
    return out + splitter.flush()


def test_splits_plain_sentences():
    assert split("Hello there. How are you? Great!") == ["Hello there.", "How are you?", "Great!"]


def test_sentence_is_ready_before_the_stream_ends():
    splitter = SentenceSplitter()
    assert splitter.feed("First one. Sec") == ["First one."]
    assert splitter.feed("ond one") == []
    assert splitter.flush() == ["Second one"]


def test_abbreviations_do_not_split():
    assert split("Dr. Smith met Mr. Jones today. They talked.") == [
        "Dr. Smith met Mr. Jones today.",
        "They talked.",
    ]
    assert split("Bring fruit, e.g. apples. Thanks.") == ["Bring fruit, e.g. apples.", "Thanks."]


def test_decimals_do_not_split():
    assert split("Pi is about 3.14 and e is 2.72. Neat.") == [
        "Pi is about 3.14 and e is 2.72.",
        "Neat.",
    ]


def test_decimal_split_across_chunks():
    assert split("It costs 3.", "50 dollars. Cheap.") == ["It costs 3.50 dollars.", "Cheap."]


def test_no_ending_punctuation_is_flushed():
    assert split("no punctuation at all") == ["no punctuation at all"]


def test_closing_quote_stays_with_its_sentence():
    assert split('She said "stop." Then she left.') == ['She said "stop."', "Then she left."]


def test_empty_stream_gives_nothing():
    assert split("", "   ") == []
