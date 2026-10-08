# Career Compass AI

A Streamlit job-search MVP with Google Jobs results through SerpAPI, local PDF/DOCX
resume matching, optional Gemini suggestions, and Glassdoor/Internshala search links.
The search experience is centered and responsive for desktop and mobile screens.
The AI career panel includes a question-and-answer chat, uses current search results as context,
and gives local role-specific guidance when Gemini is unavailable. Direct role-search questions
in chat, including fresher/entry-level requests, use SerpAPI to fetch fresh Google Jobs results
for the requested role and location. Role names are free text, so searches are not limited to a
predefined list of IT job titles; experience can be given as a number, a plus level, or a range.
Chat searches also recognize internship requests and salary phrases such as “above 7 LPA.”
Matching role titles are filtered before they appear in the job list. Salary and experience
requirements are included in the provider query, but listings may omit these details; verify them
on the job posting before applying.

## Important source limitations

- Google does not provide a public API for searching the Google Jobs listings shown
  in its consumer interface. This MVP uses SerpAPI's third-party Google Jobs engine.
  You need your own SerpAPI key and must review its pricing and terms.
- Glassdoor and Internshala direct job APIs are not assumed to be publicly available.
  The app links to searches for those sites rather than scraping them or presenting
  unverified results as live data. Direct integrations require approved provider access.
- Apply links come from the job-search provider and may lead directly to an employer or to a
  job board. The app does not invent employer URLs; it labels links as company-site applications
  only when the provider identifies them as such.

## Run locally

1. Use Python 3.10 or newer.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and provide `SERPAPI_API_KEY`.
   `GEMINI_API_KEY` is optional. For local Streamlit secrets, create
   `.streamlit/secrets.toml` with the same key names.
5. Run: `streamlit run app.py`

If a job search fails, the app distinguishes invalid API keys, exhausted quotas,
provider outages, timeouts, SSL issues, and proxy/network failures. A network
connection alone does not guarantee SerpAPI access: the key must be valid and the
account must have available searches.
If the browser already had the old generic network error saved in its session, click
**Find jobs** once more to run a fresh search and see the new provider-specific message.
If SerpAPI says **Invalid API key**, create/copy a valid key from your SerpAPI account
dashboard, replace `SERPAPI_API_KEY` in the local `.env`, and restart Streamlit. Never
paste API keys into chat or commit them to the repository. Gemini errors similarly
identify invalid credentials, unavailable models, and quota limits without displaying
the key.

The uploaded resume is parsed in memory and is not written to disk or a database.
Chat history stays in the current Streamlit session and can be cleared from the assistant panel.
If a Gemini key is configured, the user's chat question and recent messages are sent to Gemini
to answer. Resume text is only included when a resume is uploaded and the user enables its
explicit consent checkbox. Do not configure a Gemini key or enable resume sharing if you do not
want data sent to the Gemini API. Without a valid Gemini key, the assistant provides bounded
local guidance for common career topics rather than open-ended LLM answers.
The app uses the `gemini-3.6-flash` model for Gemini chat and career suggestions.
If Gemini returns a temporary model outage or timeout, chat retries with `gemini-3.5-flash`
before showing local guidance.

Resume matching is a keyword-overlap indicator, not a hiring decision or a guarantee
of suitability. Scanned PDFs need OCR and are not supported by this MVP.

## Deploy to Streamlit Community Cloud

1. Push this project to a GitHub repository.
2. Create a Streamlit Community Cloud app pointing to `app.py`.
3. Add `SERPAPI_API_KEY` (and optionally `GEMINI_API_KEY`) in the app's
   **Settings → Secrets** section using TOML syntax:

   ```toml
   SERPAPI_API_KEY = "your-key"
   GEMINI_API_KEY = "your-optional-key"
   ```

4. Deploy and test a search. Never commit `.env` or `secrets.toml`.

This MVP does not include user accounts, saved searches, scheduled alerts, or a
database. Those can be added after deciding the production hosting and data-retention
requirements.
