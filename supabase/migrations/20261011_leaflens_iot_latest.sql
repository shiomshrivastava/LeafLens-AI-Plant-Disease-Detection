-- LeafLens: latest reading for one shared demo ESP32.
-- One row is updated repeatedly; no unbounded raw sensor history.
-- No public client may read/write this table directly.
CREATE TABLE IF NOT EXISTS public.leaflens_iot_latest (
    device_id text PRIMARY KEY,
    temperature_c double precision NOT NULL CHECK (temperature_c BETWEEN -10 AND 60),
    humidity_percent double precision NOT NULL CHECK (humidity_percent BETWEEN 0 AND 100),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.leaflens_iot_latest ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.leaflens_iot_latest FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.leaflens_iot_latest TO service_role;

COMMENT ON TABLE public.leaflens_iot_latest IS
'Last ESP32 DHT11 reading, written only by the device-authenticated Supabase Edge Function.';
