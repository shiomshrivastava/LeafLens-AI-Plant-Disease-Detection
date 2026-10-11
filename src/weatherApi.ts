/** Open-Meteo non-commercial weather data. No API key is required.
 * Forecast-based advisories here are NOT official severe-weather alerts.
 * All times used for hour selection are location-local strings from Open-Meteo.
 */
export type WeatherLocation = {
  latitude: number;
  longitude: number;
  label: string;
  mode: 'auto' | 'manual';
};

export type CityOption = {
  id: number;
  latitude: number;
  longitude: number;
  name: string;
  admin1?: string;
  country?: string;
};

export type WeatherAlert = {
  kind: 'rain' | 'wind' | 'storm';
  level: 'watch' | 'caution';
  title: string;
  titleHi: string;
  message: string;
  messageHi: string;
};

export type WeatherSnapshot = {
  temperatureC: number;
  humidityPercent: number;
  feelsLikeC: number | null;
  windKmh: number | null;
  gustKmh: number | null;
  weatherCode: number | null;
  forecastPeakRainChance: number | null;
  forecastTotalPrecipitationMm: number | null;
  forecastMaxGustKmh: number | null;
  forecastHours: number;
  updatedAt: string;
  alerts: WeatherAlert[];
};

const WEATHER_URL = 'https://api.open-meteo.com/v1/forecast';
const SEARCH_URL = 'https://geocoding-api.open-meteo.com/v1/search';

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
function validCoordinate(latitude: number, longitude: number): boolean {
  return Number.isFinite(latitude) && Math.abs(latitude) <= 90 && Number.isFinite(longitude) && Math.abs(longitude) <= 180;
}

export async function searchCities(query: string, signal?: AbortSignal): Promise<CityOption[]> {
  const clean = query.trim();
  if (clean.length < 3 || clean.length > 90) throw new Error('Enter at least 3 letters of a city name.');
  const url = new URL(SEARCH_URL);
  url.searchParams.set('name', clean);
  url.searchParams.set('count', '6');
  url.searchParams.set('language', 'en');
  const res = await fetch(url.toString(), { signal });
  if (!res.ok) throw new Error('City search unavailable. Check the internet connection.');
  const json: unknown = await res.json();
  const results = (json as { results?: unknown })?.results;
  if (!Array.isArray(results)) return [];
  return results.filter((c: CityOption) => c && validCoordinate(c.latitude, c.longitude) && typeof c.name === 'string').slice(0, 6);
}

/** Uses the next 12 forecast hours, starting at the location's current local hour. */
export function parseForecast(data: unknown): WeatherSnapshot {
  const root = data as Record<string, unknown> | null;
  const current = root?.current as Record<string, unknown> | undefined;
  const hourly = root?.hourly as Record<string, unknown> | undefined;
  if (!current || !hourly) throw new Error('Incomplete forecast received.');
  const temperatureC = numberOrNull(current.temperature_2m);
  const humidityPercent = numberOrNull(current.relative_humidity_2m);
  if (temperatureC === null || humidityPercent === null) throw new Error('Current weather readings unavailable.');
  const hours = Array.isArray(hourly.time) ? hourly.time as string[] : [];
  const currentTime = typeof current.time === 'string' ? current.time : '';
  const currentHour = currentTime.slice(0, 13);
  const startIndex = hours.findIndex(h => typeof h === 'string' && h.slice(0, 13) >= currentHour);
  const first = startIndex >= 0 ? startIndex : hours.length;
  const indices = Array.from({ length: Math.min(12, Math.max(0, hours.length - first)) }, (_, i) => i + first);
  const pick = (key: string): Array<number | null> => {
    const source = Array.isArray(hourly[key]) ? hourly[key] as unknown[] : [];
    return indices.map(i => numberOrNull(source[i]));
  };
  const probabilities = pick('precipitation_probability').filter((x): x is number => x !== null);
  const rainfall = pick('precipitation').filter((x): x is number => x !== null);
  const gusts = pick('wind_gusts_10m').filter((x): x is number => x !== null);
  const codes = pick('weather_code').filter((x): x is number => x !== null);
  const peakRain = probabilities.length ? Math.max(...probabilities) : null;
  const totalRain = rainfall.length ? Math.round(rainfall.reduce((s, v) => s + Math.max(0, v), 0) * 10) / 10 : null;
  const maxGust = gusts.length ? Math.max(...gusts) : null;
  const alerts: WeatherAlert[] = [];
  if (codes.some(c => c === 95 || c === 96 || c === 99)) {
    alerts.push({
      kind: 'storm', level: 'caution', title: 'Thunderstorm possible', titleHi: 'गरज-चमक की संभावना',
      message: 'Forecast indicates possible thunderstorms within 12 hours. Check official local warnings.',
      messageHi: 'अगले 12 घंटों के पूर्वानुमान में गरज-चमक की संभावना है। आधिकारिक चेतावनी देखें।',
    });
  }
  if ((peakRain !== null && peakRain >= 70) || (totalRain !== null && totalRain >= 8)) {
    alerts.push({
      kind: 'rain', level: 'watch', title: 'Rain forecast advisory', titleHi: 'बारिश का पूर्वानुमान',
      message: `Rain may affect outdoor plants in the next 12 hours${peakRain !== null ? ` (peak probability ${Math.round(peakRain)}%)` : ''}.`,
      messageHi: `अगले 12 घंटों में बारिश हो सकती है${peakRain !== null ? ` (अधिकतम संभावना ${Math.round(peakRain)}%)` : ''}।`,
    });
  }
  if (maxGust !== null && maxGust >= 50) {
    alerts.push({
      kind: 'wind', level: 'watch', title: 'Strong wind forecast', titleHi: 'तेज़ हवा का पूर्वानुमान',
      message: `Wind gusts up to ${Math.round(maxGust)} km/h are forecast. Secure lightweight pots and supports.`,
      messageHi: `${Math.round(maxGust)} किमी/घंटा तक तेज़ हवा का अनुमान है। हल्के गमलों को सुरक्षित रखें।`,
    });
  }
  return {
    temperatureC,
    humidityPercent,
    feelsLikeC: numberOrNull(current.apparent_temperature),
    windKmh: numberOrNull(current.wind_speed_10m),
    gustKmh: numberOrNull(current.wind_gusts_10m),
    weatherCode: numberOrNull(current.weather_code),
    forecastPeakRainChance: peakRain,
    forecastTotalPrecipitationMm: totalRain,
    forecastMaxGustKmh: maxGust,
    forecastHours: indices.length,
    updatedAt: currentTime,
    alerts,
  };
}

export async function getForecast(location: WeatherLocation, signal?: AbortSignal): Promise<WeatherSnapshot> {
  if (!validCoordinate(location.latitude, location.longitude)) throw new Error('Invalid location coordinates.');
  const url = new URL(WEATHER_URL);
  url.searchParams.set('latitude', location.latitude.toFixed(5));
  url.searchParams.set('longitude', location.longitude.toFixed(5));
  url.searchParams.set('current', 'temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m,weather_code');
  url.searchParams.set('hourly', 'precipitation_probability,precipitation,wind_gusts_10m,weather_code');
  url.searchParams.set('forecast_days', '2');
  url.searchParams.set('timezone', 'auto');
  const response = await fetch(url.toString(), { signal });
  if (!response.ok) throw new Error(`Weather service unavailable (HTTP ${response.status}).`);
  const data: unknown = await response.json();
  return parseForecast(data);
}

export function readWeatherLocation(userId: string): WeatherLocation | null {
  try {
    const raw = localStorage.getItem(`leaflens-weather-location:${userId}`);
    if (!raw) return null;
    const data: WeatherLocation = JSON.parse(raw);
    return validCoordinate(data.latitude, data.longitude) && typeof data.label === 'string' &&
      (data.mode === 'auto' || data.mode === 'manual') ? data : null;
  } catch { return null; }
}

export function saveWeatherLocation(userId: string, location: WeatherLocation) {
  localStorage.setItem(`leaflens-weather-location:${userId}`, JSON.stringify(location));
}
