from redpoint import text as T


def words(s):
    return [t.word for t in T.tokenize(s)]


def test_basic_split_and_flags():
    toks = T.tokenize("Ala ma kota, a kot ma Alę. Koniec!")
    assert [t.word for t in toks] == ["Ala", "ma", "kota,", "a", "kot", "ma", "Alę.", "Koniec!"]
    assert toks[2].pause and not toks[2].sentence_end
    assert toks[6].sentence_end
    assert toks[-1].sentence_end and toks[-1].paragraph_end


def test_hyphenation_across_lines_is_joined():
    assert words("prze-\nczytać to") == ["przeczytać", "to"]


def test_dash_and_lone_punctuation_glue_to_previous_word():
    toks = T.tokenize("kot - pies ... dalej")
    assert [t.word for t in toks] == ["kot –", "pies...", "dalej"]
    assert toks[0].pause and toks[1].sentence_end


def test_paragraphs():
    toks = T.tokenize("one two.\n\nthree four")
    assert [t.paragraph_end for t in toks] == [False, True, False, True]


def test_quotes_do_not_hide_sentence_end():
    assert T.tokenize("„Tak.”")[0].sentence_end


def test_orp_positions():
    cases = {"a": "a", "to": "o", "kota": "o", "szybkość": "y", "przeczytać": "e", "najprawdopodobniej": "r"}
    for word, letter in cases.items():
        assert word[T.orp_index(word)] == letter, word


def test_orp_ignores_punctuation():
    assert "„Nowy”"[T.orp_index("„Nowy”")] == "o"
    assert T.split_word("(kot)") == ("(k", "o", "t)")
    assert T.orp_index("...") == 1


def test_timing_longer_for_sentence_ends_and_long_words():
    short = T.Token("kot")
    end = T.Token("kot.", sentence_end=True)
    long = T.Token("najprawdopodobniej")
    assert T.delay_factor(end) > T.delay_factor(short)
    assert T.delay_factor(long) > T.delay_factor(short)
    assert T.word_ms(short, 600) == 100


def test_sentence_navigation():
    toks = T.tokenize("A b c. D e f. G h.")
    assert T.next_sentence(toks, 0) == 3
    assert T.next_sentence(toks, 4) == 6
    assert T.previous_sentence(toks, 5) == 3
    assert T.previous_sentence(toks, 3) == 0
    assert T.previous_sentence(toks, 0) == 0
    assert T.next_sentence(toks, 7) == 7


def test_empty():
    assert T.tokenize("   \n\n ") == []
