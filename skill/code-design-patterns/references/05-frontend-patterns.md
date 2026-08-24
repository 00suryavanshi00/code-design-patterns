# Frontend & Component Patterns

Component design has its own pattern vocabulary. React is the reference here because it has the
richest one, but the forces apply to Vue, Svelte, SwiftUI, and Compose with different syntax.

## Contents

- [Composition over configuration](#composition-over-configuration) ·
  [Container / Presentational](#container--presentational) · [Custom Hooks](#custom-hooks) ·
  [Compound Components](#compound-components) · [Provider / Context](#provider--context)
- [Render Props](#render-props) · [HOC](#higher-order-components) ·
  [Props getters](#props-getters) · [State Reducer](#state-reducer) ·
  [Controlled vs uncontrolled](#controlled-vs-uncontrolled)
- [Error Boundary](#error-boundary) · [Suspense & data fetching](#suspense-and-data-fetching) ·
  [State machines](#state-machines-in-ui) · [Project structure](#project-structure)

---

## Composition over configuration

The single most important principle here. When a component grows boolean props —
`isLarge`, `hasIcon`, `showFooter`, `variantB` — the prop surface expands combinatorially and no
combination is tested. Accept `children` and let callers compose instead.

> A component with more than roughly five boolean props is asking to be split.

## Container / Presentational

**Force:** a component that both fetches data and renders it can only be tested with a network
mock and can only be reused with that exact data source.

Presentational components are pure functions of their props — they know nothing about APIs or
stores. Containers own fetching and state.

**The modern form:** the "container" is usually a **custom hook**, not a wrapper component. The
separation survives; the wrapper does not.

```tsx
function UserProfile({ id }: { id: string }) {
  const { user, loading, error } = useUser(id);   // the container
  if (loading) return <Spinner />;
  if (error) return <ErrorState error={error} />;
  return <UserCard user={user} />;                // pure presentation
}
```

**Payoff:** `UserCard` is testable with a literal object and reusable whether data comes from
REST, GraphQL, or a fixture.

## Custom Hooks

**Force:** stateful logic (a debounce, a subscription, pagination, form state) is needed in
several components, and HOCs/render props bury it in wrapper nesting.

The default mechanism for logic reuse in modern React. No wrapper components, no prop collisions,
composable with each other.

**Rules:** name them `useX`; return an object rather than a positional array once past two values;
keep one hook to one concern — a `useEverything` hook is a god object.

## Compound Components

**Force:** a group of components (Tabs, Accordion, Select, Menu) must share state, but callers
need control over structure and ordering.

The parent holds state and shares it via context; children read it implicitly.

```tsx
<Tabs defaultValue="a">
  <Tabs.List>
    <Tabs.Trigger value="a">Overview</Tabs.Trigger>
    <Tabs.Trigger value="b">Settings</Tabs.Trigger>
  </Tabs.List>
  <Tabs.Panel value="a">…</Tabs.Panel>
</Tabs>
```

**Why it wins over a config prop:** `<Tabs items={[...]} />` cannot express "put a divider between
the second and third tab" without a new prop. Composition can.

**In the wild:** Radix UI, Headless UI, Reach UI, and most design systems built after 2020.

**Cost:** children must be used inside the parent — throw a clear error from the context hook when
they are not, rather than failing with a confusing `undefined`.

## Provider / Context

**Force:** deeply nested components need the same value (theme, current user, locale) and
prop-drilling through eight levels is unmaintainable.

**Use it for:** low-frequency, broadly-needed values.

**Do not use it as a state manager for high-frequency updates** — every consumer re-renders when
the context value changes. Split contexts by update frequency (a stable `dispatch` context
separate from a changing `state` context), or use a store with selectors (Zustand, Jotai, Redux
Toolkit) when updates are hot.

## Render Props

Pass a function that renders. Largely superseded by hooks, but still the right tool when the
shared behaviour must *influence the JSX tree itself* — virtualised lists, drag-and-drop
containers, measurement wrappers.

## Higher-Order Components

A function taking a component and returning an enhanced one. **Mostly legacy.** Problems: wrapper
hell in the tree, prop-name collisions, lost static types, and unclear provenance of props.

Reach for it only when integrating with class components or when a framework requires it
(`connect`, `withRouter`). In new code, a hook is the answer.

## Props Getters

The component exposes `getToggleProps()`/`getMenuProps()` that return the correct props
(including `aria-*`, event handlers, and refs) with the caller's own props merged in. Gives the
caller full control of markup while keeping accessibility correct.

**In the wild:** Downshift. This is the pattern that makes headless UI libraries usable.

## State Reducer

**Force:** consumers of a reusable component need to override its internal state transitions, not
just its appearance.

The component accepts a reducer that intercepts its state changes — "when the user selects an
item, do the default thing but keep the menu open".

Advanced and rarely needed; the mark of a mature component library API.

## Controlled vs Uncontrolled

Every stateful component must decide: does the caller own the value (`value` + `onChange`) or does
the component (`defaultValue`)? Support both, and pick based on whether `value` is `undefined` at
mount — but never switch mid-life, which produces React's classic warning.

Document which one the component is. Ambiguity here is a top source of bugs in shared components.

## Error Boundary

**Force:** one component throwing during render should not blank the entire application.

Wrap route segments and independent widgets so a failure is contained and shows a recovery UI.
Note the limitation: error boundaries catch render-phase errors, not errors in event handlers or
async code — those need their own handling.

Place them at meaningful blast-radius boundaries: per route, per dashboard widget. One at the app
root only gives you a full-page error, which is the outcome you were trying to avoid.

## Suspense and Data Fetching

Move loading states out of every component's body and into declarative boundaries. Server
Components push data fetching to the server entirely, removing the client waterfall.

**The pattern to avoid:** the request waterfall — a parent fetches, renders a child, which then
fetches. Hoist fetches or use a loader that starts them in parallel.

## State Machines in UI

**Force:** a component with `isLoading`, `isError`, `isSuccess`, `isRetrying` booleans allows 16
combinations, most of them impossible, and bugs live in the impossible ones.

Model as one state variable with explicit transitions. Checkout, onboarding, multi-step forms, and
media players are the classic candidates. XState formalises it, but a `useReducer` with a
`switch` on state is often enough.

This is the frontend expression of "make illegal states unrepresentable".

## Project Structure

Two structures actually scale:

- **Feature-based** — group by domain (`features/checkout/{ui,model,api}`), not by technical kind
  (`components/`, `hooks/`, `utils/`). A feature is deleted or moved in one directory.
- **Feature-Sliced Design** — the formalised version with layers (`shared → entities → features →
  widgets → pages → app`) and a rule that imports only point downward, preventing cycles.

`components/` + `containers/` + `utils/` at the root stops working around 50 components: every
change touches four directories, and `utils/` becomes a junk drawer.

**The one rule worth enforcing:** dependencies point in one direction. Shared code never imports
feature code.
