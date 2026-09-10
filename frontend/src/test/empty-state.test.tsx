/**
 * EmptyState: the single shape every page uses for "nothing here yet".
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState, EmptyTableRow } from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders the title, the description and the action", () => {
    render(
      <EmptyState
        title="No targets yet"
        description="Add the people supporters will be connected to."
        action={<button>Add Target</button>}
      />
    );

    expect(screen.getByText("No targets yet")).toBeInTheDocument();
    expect(
      screen.getByText("Add the people supporters will be connected to.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Target" })).toBeInTheDocument();
  });

  it("renders inside a table row spanning every column", () => {
    render(
      <table>
        <tbody>
          <EmptyTableRow colSpan={4} title="No users yet" />
        </tbody>
      </table>
    );

    expect(screen.getByText("No users yet")).toBeInTheDocument();
    expect(screen.getByRole("cell")).toHaveAttribute("colspan", "4");
  });
});
