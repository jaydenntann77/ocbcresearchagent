"""The source drawer's highlight covers the whole cited excerpt, including the words at the end of a sentence."""
import fitz

from app.docs.highlight import MIN_WORDS, highlight, runs

SENTENCE = ("USDSGD rose following hotter-than-expected US CPI, which lifted the broader USD and US Treasury "
            "yields.")


def test_runs_cover_every_word():
    words = SENTENCE.split()                                           # 15 words
    got = runs(words, 10)
    assert got[0] == words[:10] and got[-1][-1] == words[-1]
    assert {w for r in got for w in r} == set(words)
    assert all(len(r) >= MIN_WORDS for r in got)
    assert runs(words[:7], 10) == [words[:7]]                          # shorter than a run: searched whole
    assert runs(words[:11], 10)[-1] == words[8:11]                     # a one-word tail borrows to MIN_WORDS


def _page_with(text):
    doc = fitz.open()
    page = doc.new_page(width=420, height=300)
    page.insert_textbox(fitz.Rect(40, 40, 380, 260), text, fontsize=12)
    return doc, page


def test_sentence_tail_is_highlighted():
    doc, page = _page_with("USDSGD. Consolidation. " + SENTENCE + " The move underscores the pair's sensitivity.")
    assert highlight(page, SENTENCE) >= 2
    marked = [a.rect for a in page.annots()]
    tail = page.search_for("Treasury yields")[0]
    assert any(r.intersects(tail) for r in marked), "the last words of the sentence are not highlighted"
    other = page.search_for("underscores")[0]
    assert not any(r.intersects(other) for r in marked), "text outside the excerpt was highlighted"
    doc.close()


def test_table_row_and_short_parts():
    doc, page = _page_with("USD-SGD 1.2892 1.2800 1.2750 1.2700 1.2650 1.2600\nNote: see below.")
    assert highlight(page, "USD-SGD | 1.2892 | 1.2800 | 1.2750 | 1.2700 | 1.2650 | 1.2600") >= 1
    assert highlight(page, "Note:") == 0                               # fewer than three words: not searched
    doc.close()


def test_a_run_that_is_not_found_is_retried_in_smaller_pieces():
    """The excerpt's table header says "Instrument" where the PDF says "Currency Pair": the horizon dates are
    still highlighted, all of them."""
    doc, page = _page_with("Currency Pair Current (16 Nov) Dec-26 Mar-27 Jun-27 Sep-27 Dec-27")
    highlight(page, "Instrument | Current (16 Nov) | Dec-26 | Mar-27 | Jun-27 | Sep-27 | Dec-27")
    marked = [a.rect for a in page.annots()]
    for h in ("Dec-26", "Mar-27", "Dec-27"):
        assert any(r.intersects(page.search_for(h)[0]) for r in marked), h
    doc.close()
