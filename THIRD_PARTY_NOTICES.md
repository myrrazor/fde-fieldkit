# Third-party notices

Fieldkit's original code is licensed under [MIT](LICENSE). Bundled third-party
materials keep the notices and licenses below. Dependency packages installed
by uv retain their own upstream licenses.

| Material | Used in | Upstream and notice |
|---|---|---|
| IBM Plex Sans and Mono | Self-hosted site fonts | [IBM/plex](https://github.com/IBM/plex), [SIL OFL 1.1](licenses/IBM-Plex-OFL.txt) |
| no-ai-slop phrase rules | Tell's bundled lexicon | [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop), [MIT](licenses/no-ai-slop-MIT.txt) |
| Faker English name data | Core PII name lists and synthetic fixtures | [joke2k/faker](https://github.com/joke2k/faker), [MIT](licenses/Faker-MIT.txt) |

The IBM notice includes the reserved font name "Plex". A copy of the OFL is also
beside the fonts at `site/fonts/OFL.txt`. Fieldkit's MIT grant does not relicense
those font files.

The original source identifies the Tell lexicon as derived from no-ai-slop and
the name lists as generated from Faker's `en_US` person provider. The exact
historical no-ai-slop content revision was not recorded. The upstream license
text was verified at commit `000650b156983f5159695b441477f4e63b25dc85`.
Faker's installed fixture-generation version is 37.12.0, corresponding to
upstream tag `v37.12.0` at `949a8d6ff538b86a6a40b2082beaeade480e891a`.
IBM's license text was verified at `bf260093582f04622aacc1e9f9ca604d7ccd0c42`;
the original font-download revision was not recorded.

The shared working indicator credits Jakub Antalik's `thinking-orbs` for visual
inspiration. Fieldkit implements its own canvas animation and does not bundle
that package. The source provenance comment is preserved.

Contributor names in these upstream copyright notices identify third-party
rights holders. They are intentionally retained attribution.
