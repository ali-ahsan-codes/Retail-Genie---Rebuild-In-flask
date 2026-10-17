
import {genkit} from 'genkit';


// Configure Genkit with no default plugins or model,
// as the Google AI plugin (which provides Gemini) is being removed.
export const ai = genkit({
  // plugins: [], // No plugins by default now
  // model: undefined, // No default model specified
});

