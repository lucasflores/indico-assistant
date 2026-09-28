def test_chainlit_is_the_pinned_release():
    import chainlit
    assert chainlit.__version__ == "2.12.0"
