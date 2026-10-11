import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL?.trim();
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();

export const isConfigured = Boolean(
  url?.startsWith('https://') && url.endsWith('.supabase.co') &&
    publishableKey?.startsWith('sb_publishable_'),
);

// Supabase publishes this key for browser clients. Never use secret/service_role keys here.
export const supabase = isConfigured
  ? createClient(url!, publishableKey!, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null;
