# Synthetic fixtures

These files are generated examples for tests and demonstrations, not customer
records. `make_fixtures.py` uses a fixed random seed and Faker's English name
provider. Copies of the customer CSVs and log are also in `examples/`.

Emails use the reserved `example.com` domain. Names, phone numbers, SSNs, card
numbers, IP addresses, dates, and account activity are generated. Some values
are deliberately valid in shape, including Luhn-valid card numbers, because
the PII detector must recognize positive examples. They are not assigned
identities, reachable contact details, or usable payment credentials.

Secret-looking log strings are deliberately inert fixtures. Repeated-zero token
values exercise prefix detection; the AWS example is the provider's documented
example identifier, and the private-key marker contains no key material.
Never substitute a real credential or try to authenticate with a fixture.

`human_sample.md` and `slop_sample.md` are fictional writing samples. The Excel
fixture uses openpyxl metadata and contains generated inventory rows.

The generated name lists retain [Faker's MIT notice](../../licenses/Faker-MIT.txt).
