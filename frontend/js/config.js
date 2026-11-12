// Agent Bank frontend config.
// LIVE=false runs the built-in simulation. LIVE=true (or open the page with ?live=1) talks to the backend.
window.AB_CONFIG = {
  LIVE: false,
  API: 'http://localhost:8000',   // FastAPI base URL
  WS: 'ws://localhost:8000/ws'    // WebSocket URL
};