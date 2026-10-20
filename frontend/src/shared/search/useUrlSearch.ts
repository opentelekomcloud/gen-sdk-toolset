import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

/** Search text kept in `?q=`, written 300 ms after typing stops. */
export function useUrlSearch() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const [input, setInput] = useState(q);

  useEffect(() => {
    const timer = setTimeout(
      () =>
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            if (input) next.set("q", input);
            else next.delete("q");
            return next;
          },
          { replace: true },
        ),
      300,
    );
    return () => clearTimeout(timer);
  }, [input, setSearchParams]);

  return { q, input, setInput };
}
