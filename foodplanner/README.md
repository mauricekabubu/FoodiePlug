# FoodiePlug

## Google sign-in setup

Google OAuth credentials are read from `GOOGLE_OAUTH_CLIENT_ID` and
`GOOGLE_OAUTH_CLIENT_SECRET`. Copy `.env.example` to `.env` and set these
values; never commit `.env`.

Create a Google OAuth 2.0 **Web application** client. For local development,
add `http://localhost:8000` as an authorized JavaScript origin and
`http://localhost:8000/accounts/google/login/callback/` as an authorized
redirect URI. If you access the development server as `127.0.0.1`, add that
origin and its matching callback URI as well.

For production, add the public HTTPS origin and the exact callback URI
`https://<your-production-host>/accounts/google/login/callback/` to the
client's authorized origins and redirect URIs. The deployed host and HTTPS
scheme must match the URI Django generates.

Run database migrations and start the local server with:

```powershell
python manage.py migrate
python manage.py runserver
```

## Database performance and pagination

The food library, pantry, meal library (including favorites and archive),
shopping-list index and shopping-list items, budget history, and budget expense history use bounded,
deterministically ordered pages. Search, category, status, and sort choices
remain in the page links. Invalid page numbers fall back to the first or last
valid page. Current page sizes are 24 foods, 20 pantry items, 12 meals, 12
shopping lists, 20 items per shopping list, 10 budgets, and 15 expenses.

Indexes are limited to observed access patterns: active food and meal listings;
user-scoped pantry expiry, shopping-list recency, budgets, and price history;
shopping-item state within a list; recent AI conversations and messages; meal
preference flags; and budget-entry history. The composite indexes also cover the corresponding foreign-key
prefix lookups, so redundant single-column foreign-key indexes are omitted for
those fields. These are standard B-tree indexes supported by both SQLite and
PostgreSQL. The food-name `icontains` search remains a contains search and is
not made faster by a standard B-tree index.

Apply the new index-only schema migrations using the normal, non-destructive
workflow:

```powershell
python manage.py migrate
```

The pantry query joins food and category in one query to avoid per-row related
lookups. Budget totals and weekly chart data are aggregated in the database;
the expense table is paginated separately. These changes have regression
coverage, but index and end-to-end latency improvements have not been benchmarked
against production-sized data.