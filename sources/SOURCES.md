# Official sources for Veritas

Veritas doesn't come preloaded with "all the laws." U.S. law includes federal statutes, federal regulations, 50 state codes, local ordinances, and a vast body of court decisions, and it changes constantly. A copy loaded once would soon be out of date, and outdated legal information can cost people their homes, jobs, or cases.

Instead, Veritas works like a careful researcher: you load the official texts that matter for your work, labeled with where they apply and when you copied them. Veritas cites them and shows those labels in its answers. Legal answers with no official source behind them are capped at low confidence, so Veritas will say it isn't sure.

## How to add an official source

1. Open the official page below and copy the section you need into a plain text file (for example, `pa-landlord-tenant.txt`).
2. Import it word-for-word, labeled with its jurisdiction and today's date:
   ```bash
   python -m veritas import pa-landlord-tenant.txt --official --jurisdiction PA --as-of 2026-09-10
   ```
3. When a law changes, import the new version and use `python -m veritas forget <id>` to remove the old one.

Official texts are never summarized on import, because rewording a law can change its meaning.

## Founding documents and moral standards

| Source | Official link |
|---|---|
| Universal Declaration of Human Rights | https://www.un.org/en/about-us/universal-declaration-of-human-rights |
| Declaration of Independence | https://www.archives.gov/founding-docs/declaration-transcript |
| U.S. Constitution | https://www.archives.gov/founding-docs/constitution-transcript |
| Bill of Rights | https://www.archives.gov/founding-docs/bill-of-rights-transcript |

## Federal law

| Source | What it contains | Official link |
|---|---|---|
| United States Code | Federal statutes | https://uscode.house.gov |
| Electronic Code of Federal Regulations | Federal agency rules | https://www.ecfr.gov |
| Congress.gov | Bills and new laws | https://www.congress.gov |
| GovInfo | Official federal publications | https://www.govinfo.gov |
| U.S. Supreme Court | Opinions | https://www.supremecourt.gov |
| CourtListener (Free Law Project) | Free searchable court opinions | https://www.courtlistener.com |

## Pennsylvania

| Source | What it contains | Official link |
|---|---|---|
| Pennsylvania General Assembly | Consolidated and unconsolidated statutes, and the Pennsylvania Constitution | https://www.palegis.us/statutes |
| Pennsylvania Code and Bulletin | State agency regulations and court rules | https://www.pacodeandbulletin.gov |
| Office of Open Records | Right-to-Know Law requests and appeals | https://www.openrecords.pa.gov |

Pennsylvania is still codifying its statutes, so some laws are in the Consolidated Statutes and others remain unconsolidated. Check both.

## Where to send people for real help

Veritas gives legal information, not legal advice. For Pennsylvania:

- **PALawHelp.org** (https://www.palawhelp.org): free legal information and a directory of free and low-cost legal services.
- **Pennsylvania Legal Aid Network** (https://palegalaid.net/find-legal-help): free civil legal help for eligible people across the state.
- **Public defenders** handle criminal cases for people who can't afford a lawyer.

To change the referral Veritas gives, set `VERITAS_LEGAL_REFERRAL`.

## Accuracy checklist before relying on a source

- Is it from the official government site, not a copy?
- Is the date you copied it recorded with `--as-of`?
- Does it apply to the right place (federal, state, or local)?
- Has it been amended? Official sites usually show the effective date.
- Ideally, has someone at a legal aid organization reviewed the sources you're using?
