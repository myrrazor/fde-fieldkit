# Fieldkit UI screenshots

Captured on 2026-09-15 from the real local Fieldkit application with all eight
plugins installed. Each image is an unaltered 1280 × 900 browser viewport capture;
some views are scrolled to show the result. No UI, scores, or traffic were painted
into the images. All input data and notes are synthetic examples.

| Image | Input and visible result |
|---|---|
| `hub.png` | The local hub with all eight installed tools. |
| `xray.png` | `examples/customers.csv`: inferred types, null counts, and PII flags; raw values stay redacted. |
| `scrub.png` | The same fixture, default detected PII kinds, mapping off: replacement counts and a downloadable result. |
| `mimic.png` | The fixture's `customer_id`, `email`, `plan`, `mrr`, and `seats` columns: learn a spec, then generate 100 rows with seed 42. Scrolled to the controls and generated preview. |
| `datadiff.png` | `examples/customers.csv` and `examples/customers_v2.csv`: schema and keyed row changes. |
| `debrief.png` | An isolated database with four notes prefixed `Sample:`: a win, blocker, decision, and next step. Scrolled to the weekly report. |
| `tell.png` | `tests/fixtures/slop_sample.md`: local stylometric signals and highlighted phrases. Offline stays checked; remote adapters are skipped and ML is off. |
| `netwatch.png` | An isolated database containing a real supervised generic Python command. It makes two HTTP requests through Netwatch to a loopback sample server. No external or customer traffic is shown. |
| `awcp.png` | `examples/awcp/support-ticket-triage.yaml` and `examples/awcp/support-triage-golden.yaml` in Eval mode: scoring recorded sample cases. No model ran. |

## Reproduce

Run `uv sync --locked --all-packages`, then start `uv run fieldkit serve` and open
the printed loopback URL. Use fresh paths for `FIELDKIT_DEBRIEF_DB` and
`FIELDKIT_NETWATCH_DB` before launching the app; never capture a personal database
or another engineer's live session.

Use the input files and actions listed above. For the narrow Mimic input, select
the five listed columns from the synthetic customer fixture without changing
their values. The sample Debrief notes describe a CSV import, pending staging VPN
access, synthetic demo data, and a deployment checklist. Their timestamps are
example capture timestamps, not evidence of a customer engagement.

For Netwatch, supervise a generic client with `fieldkit netwatch run --agent
generic`. Point its HTTP proxy at the invocation's `HTTP_PROXY`, clear proxy
bypass settings inside that client, and contact only a temporary HTTP server
bound to `127.0.0.1`. The capture uses `/sample/schema` and `/sample/report` paths
returning a small JSON sample. The displayed counts and byte totals are real
measurements of that local example, not product usage metrics or a benchmark.

Capture PNG files at the desktop viewport above with no page restyling, overlays,
or image edits. Keep readable input controls or report actions in the frame.
Run `python3 site/check_site.py` to check the files and their references. Review
the pixels for private identifiers before publishing, as text scans alone cannot
verify screenshot contents.
