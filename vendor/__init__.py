"""Matching code lifted from the jobscout crawler.

Copied rather than imported across directories: the crawler is a separate repo
that does not exist on a deployed host, and an app that only runs where a
sibling folder happens to live is not deployable. These files are the evaluated
matcher, so they are vendored deliberately and updated by re-copying.
"""
