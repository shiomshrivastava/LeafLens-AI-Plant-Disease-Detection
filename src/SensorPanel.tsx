import { useEffect, useState } from 'react';
import {
  Cloud, CloudRain, CloudSun, Compass, Droplets, LocateFixed, MapPin, RefreshCw,
  Search, ShieldAlert, Thermometer, Wifi, WifiOff, Wind, X,
} from 'lucide-react';
import type { Language } from './i18n';
import {
  getForecast, readWeatherLocation, saveWeatherLocation, searchCities,
} from './weatherApi';
import type { CityOption, WeatherLocation, WeatherSnapshot } from './weatherApi';

type SensorReading = {
  configured: boolean;
  online: boolean;
  source: string;
  temperature_c: number | null;
  humidity_percent: number | null;
  updated_at: string | null;
  age_seconds: number | null;
};

const offline: SensorReading = {
  configured: false, online: false, source: 'ESP32 + DHT11',
  temperature_c: null, humidity_percent: null, updated_at: null, age_seconds: null,
};

/** All requests for current/forecast weather are made directly from the browser.
 * ESP32 readings come from the local FastAPI backend. No weather key needed.
 */
export function SensorPanel({ apiBaseUrl, language, userId }: {
  apiBaseUrl: string; language: Language; userId: string;
}) {
  const hi = language === 'hi';
  const [reading, setReading] = useState<SensorReading>(offline);
  const [sensorChecking, setSensorChecking] = useState(true);
  const [location, setLocation] = useState<WeatherLocation | null>(() => readWeatherLocation(userId));
  const [weather, setWeather] = useState<WeatherSnapshot | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [weatherError, setWeatherError] = useState('');
  const [cityQuery, setCityQuery] = useState('');
  const [cityResults, setCityResults] = useState<CityOption[]>([]);
  const [citySearching, setCitySearching] = useState(false);
  const [cityError, setCityError] = useState('');
  const [geoLoading, setGeoLoading] = useState(false);
  const [showCitySearch, setShowCitySearch] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function update() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/iot/current`, {
          cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) throw new Error('Sensor API unavailable');
        const data = await response.json() as SensorReading;
        if (active) setReading(data);
      } catch {
        if (active) setReading(offline);
      } finally {
        if (active) setSensorChecking(false);
      }
    }
    void update();
    const timer = window.setInterval(() => void update(), 5000);
    return () => { active = false; window.clearInterval(timer); controller.abort(); };
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!location) { setWeather(null); setWeatherError(''); setWeatherLoading(false); return; }
    let active = true;
    const controller = new AbortController();
    async function updateWeather() {
      if (active) setWeatherLoading(true);
      try {
        const data = await getForecast(location!, controller.signal);
        if (active) { setWeather(data); setWeatherError(''); }
      } catch (error) {
        if (active) {
          setWeather(null); // Never keep showing stale weather as current data.
          setWeatherError(error instanceof Error ? error.message : 'Weather data unavailable.');
        }
      } finally { if (active) setWeatherLoading(false); }
    }
    void updateWeather();
    const timer = window.setInterval(() => void updateWeather(), 10 * 60 * 1000);
    return () => { active = false; window.clearInterval(timer); controller.abort(); };
  }, [location, refreshKey]);

  function selectLocation(next: WeatherLocation) {
    saveWeatherLocation(userId, next);
    setLocation(next);
    setCityResults([]);
    setCityError('');
    setShowCitySearch(false);
  }

  function detectLocation() {
    if (!navigator.geolocation) { setWeatherError(hi ? 'इस ब्राउज़र में लोकेशन उपलब्ध नहीं है। शहर चुनें।' : 'Location unavailable in this browser. Select a city.'); setShowCitySearch(true); return; }
    setGeoLoading(true); setCityError('');
    navigator.geolocation.getCurrentPosition(
      coords => {
        setGeoLoading(false);
        selectLocation({ latitude: coords.coords.latitude, longitude: coords.coords.longitude,
          label: hi ? 'मेरी वर्तमान लोकेशन' : 'My current location', mode: 'auto' });
      },
      () => { setGeoLoading(false); setWeatherError(hi ? 'लोकेशन की अनुमति नहीं मिली। कृपया शहर चुनें।' : 'Location access denied or unavailable. Please select a city.'); setShowCitySearch(true); },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 5 * 60 * 1000 },
    );
  }

  async function findCity(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCitySearching(true); setCityResults([]); setCityError('');
    try {
      const cities = await searchCities(cityQuery);
      setCityResults(cities);
      if (!cities.length) setCityError(hi ? 'शहर नहीं मिला। दूसरा नाम आज़माएँ।' : 'City not found. Try another name.');
    } catch (error) {
      setCityError(error instanceof Error ? error.message : 'City search failed.');
    } finally { setCitySearching(false); }
  }

  const sensorOnline = reading.online && reading.temperature_c !== null && reading.humidity_percent !== null;
  const source = sensorOnline ? 'DHT11' : weather ? 'Open-Meteo' : null;
  const temperature = sensorOnline ? reading.temperature_c : weather?.temperatureC ?? null;
  const humidity = sensorOnline ? reading.humidity_percent : weather?.humidityPercent ?? null;
  const updateText = sensorOnline && reading.updated_at
    ? new Date(reading.updated_at).toLocaleTimeString(hi ? 'hi-IN' : 'en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : weather?.updatedAt?.replace('T', ' ') || '—';

  return <section className="card environment-card" aria-label="LeafLens IoT and weather monitoring">
    <div className="sensor-card-heading">
      <div>
        <span className="sensor-eyebrow">LEAFLENS · IoT + WEATHER</span>
        <h2>{hi ? 'मौसम और वातावरण' : 'Weather & Environment'}</h2>
        <p>{hi ? 'सेंसर उपलब्ध होने पर उसी की रीडिंग; बंद होने पर मौसम API का डेटा।' : 'Local DHT11 readings when online; outdoor weather as fallback.'}</p>
      </div>
      <span className={`sensor-status ${sensorOnline ? 'sensor-online' : 'sensor-offline'}`} role="status">
        {sensorOnline ? <Wifi size={16}/> : <WifiOff size={16}/>}
        {sensorOnline ? (hi ? 'DHT11 ऑनलाइन' : 'DHT11 Online') : sensorChecking ? (hi ? 'जाँच जारी…' : 'Checking sensor…') : (hi ? 'DHT11 ऑफलाइन' : 'DHT11 Offline')}
      </span>
    </div>

    <div className="weather-location-row">
      <div className="weather-location-info"><MapPin size={17}/><span>{location ? location.label : (hi ? 'मौसम के लिए लोकेशन चुनें' : 'Select a location for weather')}</span></div>
      <div className="weather-location-actions">
        <button type="button" className="secondary-action" onClick={detectLocation} disabled={geoLoading}>
          <LocateFixed size={16}/> {geoLoading ? (hi ? 'खोज रहे हैं…' : 'Locating…') : (hi ? 'मेरी लोकेशन' : 'My Location')}
        </button>
        <button type="button" className="secondary-action" onClick={() => setShowCitySearch(v => !v)}>
          <Search size={16}/> {hi ? 'शहर चुनें' : 'Choose City'}
        </button>
        {location && <button type="button" className="weather-refresh" onClick={() => setRefreshKey(n => n + 1)} aria-label="Refresh weather" title="Refresh weather" disabled={weatherLoading}><RefreshCw size={17}/></button>}
      </div>
    </div>

    {showCitySearch && <div className="weather-city-picker">
      <form onSubmit={e => void findCity(e)} className="weather-city-form">
        <label className="sr-only" htmlFor="weather-city-search">City</label>
        <input id="weather-city-search" value={cityQuery} onChange={e => setCityQuery(e.target.value)} placeholder={hi ? 'शहर का नाम (जैसे Bhopal)' : 'Type a city, e.g. Bhopal'} maxLength={90}/>
        <button type="submit" className="primary-action" disabled={citySearching || cityQuery.trim().length < 3}>{citySearching ? '…' : (hi ? 'खोजें' : 'Search')}</button>
        <button type="button" className="weather-refresh" onClick={() => setShowCitySearch(false)} title="Close city search"><X size={16}/></button>
      </form>
      {cityError && <p className="weather-inline-error" role="alert">{cityError}</p>}
      {cityResults.length > 0 && <div className="weather-city-results">
        {cityResults.map(city => <button type="button" key={city.id} onClick={() => selectLocation({ latitude: city.latitude, longitude: city.longitude, label: [city.name, city.admin1, city.country].filter(Boolean).join(', '), mode: 'manual' })}><MapPin size={14}/>{[city.name, city.admin1, city.country].filter(Boolean).join(', ')}</button>)}
      </div>}
    </div>}

    <div className="sensor-metrics">
      <div className="sensor-metric"><span className="sensor-metric-icon"><Thermometer size={24}/></span>
        <div><span className="sensor-metric-label">{hi ? 'तापमान' : 'Temperature'}</span><strong>{temperature !== null ? `${temperature.toFixed(1)}°C` : '—'}</strong></div></div>
      <div className="sensor-metric"><span className="sensor-metric-icon humidity"><Droplets size={24}/></span>
        <div><span className="sensor-metric-label">{hi ? 'आर्द्रता' : 'Humidity'}</span><strong>{humidity !== null ? `${humidity.toFixed(1)}%` : '—'}</strong></div></div>
    </div>
    <p className="sensor-note">
      {source
        ? (hi ? `डेटा स्रोत: ${source === 'DHT11' ? 'स्थानीय DHT11 सेंसर' : 'Open-Meteo (बाहरी मौसम)'} · अपडेट: ${updateText}` : `Data source: ${source === 'DHT11' ? 'Local DHT11 sensor' : 'Open-Meteo (outdoor weather)'} · Updated: ${updateText}`)
        : sensorChecking || weatherLoading ? (hi ? 'मौसम और सेंसर जाँचे जा रहे हैं…' : 'Checking sensor and weather…')
          : (hi ? 'कोई रीडिंग उपलब्ध नहीं है। सेंसर या मौसम लोकेशन जाँचें।' : 'No readings available. Check your sensor or select a weather location.')}
    </p>
    {!sensorOnline && weather && <p className="weather-fallback-note"><WifiOff size={15}/> {hi ? 'DHT11 ऑफलाइन: बाहरी मौसम डेटा दिखाया जा रहा है। यह कमरे/खेत के सेंसर की रीडिंग नहीं है।' : 'DHT11 offline: showing outdoor weather for the selected location, not a reading from your room or field.'}</p>}
    {weatherError && <p className="weather-inline-error" role="alert">{weatherError}</p>}

    <div className="weather-divider"/>
    <div className="weather-section-head"><div><CloudSun size={21}/><strong>{hi ? 'मौजूदा मौसम और अगले 12 घंटे' : 'Current Weather & Next 12 Hours'}</strong></div><span>{weatherLoading ? (hi ? 'अपडेट हो रहा है…' : 'Updating…') : (hi ? 'स्थान आधारित पूर्वानुमान' : 'Location-based forecast')}</span></div>
    {weather ? <>
      <div className="weather-metrics-grid">
        <div className="weather-mini-stat"><Cloud size={19}/><span>{hi ? 'महसूस होने वाला तापमान' : 'Feels like'}</span><strong>{weather.feelsLikeC !== null ? `${weather.feelsLikeC.toFixed(1)}°C` : '—'}</strong></div>
        <div className="weather-mini-stat"><Wind size={19}/><span>{hi ? 'हवा की गति' : 'Wind speed'}</span><strong>{weather.windKmh !== null ? `${Math.round(weather.windKmh)} km/h` : '—'}</strong></div>
        <div className="weather-mini-stat"><CloudRain size={19}/><span>{hi ? 'बारिश की अधिकतम संभावना' : 'Peak rain chance'}</span><strong>{weather.forecastPeakRainChance !== null ? `${Math.round(weather.forecastPeakRainChance)}%` : '—'}</strong></div>
        <div className="weather-mini-stat"><Compass size={19}/><span>{hi ? 'अधिकतम तेज़ हवा' : 'Peak wind gust'}</span><strong>{weather.forecastMaxGustKmh !== null ? `${Math.round(weather.forecastMaxGustKmh)} km/h` : '—'}</strong></div>
      </div>
      <div className="weather-advisories"><strong><ShieldAlert size={18}/>{hi ? 'मौसम सलाह' : 'Weather Advisories'}</strong>
        {weather.alerts.length ? weather.alerts.map(alert => <div key={alert.kind} className={`weather-advisory ${alert.level === 'caution' ? 'weather-advisory-high' : ''}`}>
          <strong>{hi ? alert.titleHi : alert.title}</strong><p>{hi ? alert.messageHi : alert.message}</p>
        </div>) : <p className="weather-clear">{hi ? 'अगले 12 घंटों के पूर्वानुमान में इस ऐप की बारिश/हवा/तूफ़ान सीमा पार नहीं हुई है।' : 'No rain, wind or thunderstorm thresholds triggered in the next 12-hour forecast.'}</p>}
      </div>
    </> : <div className="weather-not-set"><CloudSun size={24}/><p>{location ? (weatherLoading ? (hi ? 'मौसम लोड हो रहा है…' : 'Loading weather…') : (hi ? 'मौसम उपलब्ध नहीं है। दोबारा कोशिश करें।' : 'Weather unavailable. Please retry.')) : (hi ? 'मौसम, बारिश और हवा का पूर्वानुमान देखने के लिए लोकेशन चुनें।' : 'Choose your location to see weather, rain forecasts and wind advisories.')}</p></div>}
    <p className="weather-attribution">{hi ? 'मौसम पूर्वानुमान, आधिकारिक आपदा चेतावनी नहीं है।' : 'Forecast advisories are not official emergency warnings.'} · <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Weather data: Open-Meteo</a> · <a href="https://geonames.org/" target="_blank" rel="noopener noreferrer">Location data: GeoNames</a></p>
  </section>;
}
