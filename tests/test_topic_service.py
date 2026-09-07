from studygraph.topic_service import analyze_document_topics


def test_topic_analysis_separates_lecture_title_and_metadata() -> None:
    analysis = analyze_document_topics(
        filename="AD_03_Graphen.pdf",
        text=(
            "Graphen\n"
            "Algorithmen und Datenstrukturen\n"
            "VU 186.866, 5.5h, 8 ECTS\n"
            "Vorlesungsfolien\n"
            "Knoten\n"
            "Kanten\n"
            "Breitensuche\n"
            "Die Breitensuche besucht Knoten schichtweise.\n"
        ),
    )

    assert analysis.document_title == "Algorithmen und Datenstrukturen"
    assert "VU 186.866, 5.5h, 8 ECTS" in analysis.metadata_lines
    assert "Vorlesungsfolien" in analysis.metadata_lines
    topic_names = {topic.name for topic in analysis.topics}
    assert "Graphen" in topic_names
    assert "Knoten" in topic_names
    assert "Kanten" in topic_names
    assert "Algorithmen und Datenstrukturen" not in topic_names
    assert any(
        relation.source == "Graphen" and relation.target == "Knoten"
        for relation in analysis.relations
    )


def test_topic_analysis_ignores_prose_lines_and_deduplicates_topics() -> None:
    analysis = analyze_document_topics(
        filename="calculus.pdf",
        text=(
            "Ableitungen\n"
            "Ableitungen\n"
            "Die Ableitung beschreibt die lokale Änderungsrate einer Funktion.\n"
            "Integrale.\n"
        ),
    )

    assert [topic.name for topic in analysis.topics] == ["Ableitungen"]
