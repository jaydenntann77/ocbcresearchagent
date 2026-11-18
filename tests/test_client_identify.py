import pytest

from app.clientdata.generate import generate
from app.clientdata.identify import identify

BOOK = generate()


def ident(q):
    return identify(q, BOOK.clients, BOOK.contacts)


@pytest.mark.parametrize("question, client, contact, research", [
    ("Jimmy from company A asks for the USDSGD forecast", "Harbourline Logistics Pte Ltd", "Jimmy Tan",
     "The USDSGD forecast"),
    ("Jimmy from Meridian wants OCBC's view on AUD/USD", "Meridian Foods Holdings Ltd", "Jimmy Lee",
     "OCBC's view on AUD/USD"),
    ("Meridian Food Industries asked about the ringgit outlook", "Meridian Food Industries Sdn Bhd", None,
     "The ringgit outlook"),
    ("Harbourline's treasurer wants the USD/CNH forecast through 2027", "Harbourline Logistics Pte Ltd", None,
     "The USD/CNH forecast through 2027"),
    ("Grace from Kestrel asked: what does OCBC see for USD/JPY?", "Kestrel Semiconductor Pte Ltd", "Grace Lim",
     "What does OCBC see for USD/JPY?"),
    ("Henry Wong is asking about gold", "Mr Henry Wong", "Henry Wong", "Gold"),
])
def test_clear_matches_and_name_removed_from_research_question(question, client, contact, research):
    r = ident(question)
    assert r.status == "match"
    assert r.candidates[0].client_name == client
    assert r.candidates[0].contact_name == contact
    assert r.research_question == research


def test_first_name_alone_is_ambiguous():
    r = ident("Jimmy asks for the USD/SGD forecast")
    assert r.status == "ambiguous"
    assert {c.contact_name for c in r.candidates} == {"Jimmy Tan", "Jimmy Lee", "Jimmy Seah"}
    assert r.research_question == "The USD/SGD forecast"


def test_similar_company_names_are_ambiguous():
    r = ident("Meridian asked about the ringgit outlook")
    assert r.status == "ambiguous"
    assert len({c.client_id for c in r.candidates}) == 2


def test_no_client_leaves_question_untouched():
    q = "What is OCBC's forecast for USD/SGD?"
    r = ident(q)
    assert r.status == "none" and r.candidates == [] and r.research_question == q


def test_lowercase_first_names_do_not_match():
    # "grace" / "ben" as ordinary words must not be read as contacts
    assert ident("by the grace of the Fed, will ben bernanke-era QE return? USD/SGD").status == "none"


@pytest.mark.parametrize("question, client, contact", [
    ("jimmy from habourline logsitic asked me about usd/sgd", "Harbourline Logistics Pte Ltd", "Jimmy Tan"),
    ("Rachel from habourline wants usd/cnh", "Harbourline Logistics Pte Ltd", "Rachel Goh"),
    ("kestral semi wants usd/jpy", "Kestrel Semiconductor Pte Ltd", None),
    ("pinacle asset mgmt wants eur/usd", "Pinnacle Asset Management", None),
])
def test_misspelt_company_still_matches(question, client, contact):
    r = ident(question)
    assert r.status == "match"
    assert (r.candidates[0].client_name, r.candidates[0].contact_name) == (client, contact)


def test_misspelt_similar_name_stays_ambiguous():
    assert ident("meridan asked about aud").status == "ambiguous"


@pytest.mark.parametrize("question", ["what about the silver outlook", "the logistics outlook for asia",
                                      "grace period on the forward", "jimmy wants usd/sgd"])
def test_no_typo_match_on_ordinary_words(question):
    # Only a capitalised first name, or one next to its company, counts as a person.
    assert ident(question).status == "none"
