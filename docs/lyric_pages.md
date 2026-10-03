# Optional lyric page optimization

For pause- and phrase-aware reflow, use the separate
[Intelligent page breaks](intelligent_page_breaks.md) toolbar action.

Tools > Optimize lyric pages splits existing long phrases at whole-word
boundaries. Defaults are 30 visible characters, 8 notes and 3 seconds of
note span per page, based on the original-song corpus described in
[Lyric page corpus](lyric_page_corpus.md). These are conservative readability
targets, not proven renderer or file-format limits. Proportional fonts, screen layout and unusually long
individual words mean character counts cannot guarantee pixel-perfect fit.

The operation is explicit and undoable. It never runs automatically during
UltraStar import/export. Existing phrase boundaries and their manual switch
times are preserved. New boundaries use the established writer's automatic
page-switch timing. Notes, pitches, syllable text, lengths and timing are
unchanged; all continuation notes belonging to one word stay on the same
page. Indivisible words or melismas exceeding a limit are reported rather
than cut or shortened. Reapplying the same limits is idempotent.

The writer also retains a word-end flag if any continuation in its group
already marked that ending. A later continuation with end_word=false must
not erase an earlier true flag and merge adjacent displayed words.

Local synthetic regression tests cover character/note/time limits, unchanged
musical fields and text, manual page times, melisma boundaries, repeated
application and invalid limits. Corpus-analysis tests use freshly generated
synthetic IXB pairs and check explicit page boundaries and deduplication.
This is not a substitute for the user's Xbox layout/playback verification.
Original source files, screenshots and prepared projects are not committed.
