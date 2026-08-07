import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * URL-synced state: reads `key` from the query string (falling back to
 * `defaultValue`) and writes changes back via replace-navigation so
 * filters/tabs are shareable and survive reloads without spamming history.
 */
export function useSearchParamState(
  key: string,
  defaultValue = '',
): [string, (value: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const value = searchParams.get(key) ?? defaultValue;

  const setValue = useCallback(
    (next: string) => {
      setSearchParams(prev => {
        const params = new URLSearchParams(prev);
        if (next === '' || next === defaultValue) params.delete(key);
        else params.set(key, next);
        return params;
      }, { replace: true });
    },
    [key, defaultValue, setSearchParams],
  );

  return [value, setValue];
}
