declare module 'traceable-deep-researcher-ui' {
  import React from 'react';

  export interface TraceableDeepResearcherProps {
    apiUrl?: string;
    apiKey?: string;
    defaultPrompt?: string;
    onResultsChange?: (results: any) => void;
    theme?: any;
  }

  export const TraceableDeepResearcher: React.FC<TraceableDeepResearcherProps>;
}