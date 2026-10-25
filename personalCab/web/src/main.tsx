import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { MotionConfig } from 'motion/react';
import { Providers } from './app/context';
import { App } from './app/App';
import '@fontsource/onest/latin-400.css';
import '@fontsource/onest/latin-500.css';
import '@fontsource/onest/latin-600.css';
import '@fontsource/onest/latin-700.css';
import '@fontsource/onest/cyrillic-400.css';
import '@fontsource/onest/cyrillic-500.css';
import '@fontsource/onest/cyrillic-600.css';
import '@fontsource/onest/cyrillic-700.css';
import '@fontsource/unbounded/latin-600.css';
import '@fontsource/unbounded/latin-700.css';
import '@fontsource/unbounded/cyrillic-600.css';
import '@fontsource/unbounded/cyrillic-700.css';
import './styles/index.css';
import { ServerCabinet } from './app/ServerPages';
import './styles/integrated.css';
if (import.meta.env.VITE_API_MODE === 'http') document.body.classList.add('integrated-v2');
createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <MotionConfig reducedMotion="user">
      {import.meta.env.VITE_API_MODE === 'http' ? (
        <ServerCabinet />
      ) : (
        <Providers>
          <App />
        </Providers>
      )}
    </MotionConfig>
  </BrowserRouter>,
);
