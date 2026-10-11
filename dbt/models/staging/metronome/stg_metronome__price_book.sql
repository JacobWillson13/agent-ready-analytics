select plan, item, unit, price_usd, cast(effective_from as date) as effective_from, cast(effective_to as date) as effective_to
from {{ source('metronome', 'price_book') }}
