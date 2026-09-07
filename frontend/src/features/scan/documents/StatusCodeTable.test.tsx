import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderPage } from "../../../test/render";
import type { SectionDetail } from "../../../shared/api/types";
import { StatusCodeTable } from "./StatusCodeTable";
import { DocSectionRow } from "./DocSectionRow";

/** A section as the API serves one, with only the fields the row reads. */
function section(over: Partial<SectionDetail> = {}): SectionDetail {
  return {
    name: "status_codes",
    status: "ok",
    fields_total: 0,
    fields_recognized: 0,
    fields_unknown_type: 0,
    parameters: null,
    issues: [],
    examples: [],
    status_codes: [
      { code: "200", description: "The request is successful." },
      { code: "400", description: "The request body is abnormal." },
    ],
    ...over,
  } as SectionDetail;
}

describe("the status-code table", () => {
  it("shows every code with its description", () => {
    renderPage(<StatusCodeTable section={section()} />);

    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("The request is successful.")).toBeInTheDocument();
    expect(screen.getByText("400")).toBeInTheDocument();
  });

  it("renders a code that carries no description without leaving a blank cell", () => {
    renderPage(
      <StatusCodeTable section={section({ status_codes: [{ code: "204", description: "" }] })} />,
    );

    expect(screen.getByText("204")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("the document drill-down", () => {
  it("renders status codes rather than the parameter table's empty state", () => {
    /* The section has no parameters, so without its own branch the row would
       fall through to IrTable and claim there is nothing to show. */
    renderPage(<DocSectionRow section={section()} />);
    fireEvent.click(screen.getByText(/status codes/i));

    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.queryByText(/no parameter table/i)).toBeNull();
  });

  it("still shows the parameter empty state for a section with neither", () => {
    renderPage(<DocSectionRow section={section({ name: "body", status_codes: [] })} />);
    fireEvent.click(screen.getByText(/body/i));

    expect(screen.getByText(/no parameter table/i)).toBeInTheDocument();
  });
});
