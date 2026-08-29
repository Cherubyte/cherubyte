import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    const on = () => setMatches(mql.matches);
    on();
    mql.addEventListener("change", on);
    return () => mql.removeEventListener("change", on);
  }, [query]);
  return matches;
}

/** < 768px — phone / small tablet portrait */
export const useIsMobile = () => useMediaQuery("(max-width: 767px)");
/** >= 1024px — comfortable desktop */
export const useIsDesktop = () => useMediaQuery("(min-width: 1024px)");
