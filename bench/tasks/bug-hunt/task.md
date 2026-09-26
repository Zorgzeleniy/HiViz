# Bug hunt: real PyJWT source, three real historical bugs reverted

This is the actual source of **PyJWT** (github.com/jpadilla/pyjwt, MIT; vendored at
2.13.0-era). Three real historical bugfixes from its history have been **reverted**
— the bugs are live again. No feature is missing; the library works, except where
it doesn't.

Find the bugs and fix them with minimal, targeted changes. Do not rewrite the
library, do not change public APIs, do not add dependencies. The verifier checks
the exact behaviors that the original upstream fixes restored:

- crafted claim values that must raise proper `PyJWTError` subclasses instead of
  leaking runtime errors;
- claim type validation that upstream added after real issue reports;
- a null-claim handling case that produced the wrong exception class.

The upstream fixes were small (a few lines each). Find them by behavior, not by
reading the changelog — there is none here.

Work strictly in the current directory. No network, no git commits.
