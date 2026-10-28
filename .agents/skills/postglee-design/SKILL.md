---
name: postglee-design
description: Use this skill when designing or editing UI pages, HTML templates, or email templates (`templates/**/*.html`) for PostGlee, a social media management platform. It features a friendly and efficient mood, with primary colors like #fb923c and a light scheme. The typography uses Sora for headings and Inter for body text, with pill buttons (`9999px`), rounded cards (`24px` / `16px`), and the official PostGlee logo header (`https://postglee.com/postglee-logo.png`).
packages:
  - name: clsx
    purpose: Tiny utility for conditionally joining class names
    kind: dependency
    curated: true
  - name: tailwind-merge
    purpose: Merge Tailwind classes without style conflicts
    kind: dependency
    curated: true
  - name: class-variance-authority
    purpose: Type-safe component style variants (CVA)
    kind: dependency
    curated: true
  - name: shadcn
    purpose: Accessible, unstyled UI primitives you copy into the project
    kind: setup
    curated: true
    command: pnpm dlx shadcn@latest add
  - name: react-feather
    purpose: To provide a set of commonly used icons for UI elements, complementing the visual design.
    kind: dependency
    curated: false
  - name: styled-components
    purpose: For creating reusable UI components with scoped styles, leveraging the defined design tokens.
    kind: dependency
    curated: false
  - name: react-spring
    purpose: To implement smooth animations and transitions as described in the motion section, enhancing user experience.
    kind: dependency
    curated: false
---
```yaml
brand: PostGlee
mood: Simple, friendly, and efficient, creating a feeling of effortless control over complex social media workflows.
scheme: light
logo: "https://postglee.com/postglee-logo.png"
colors:
  primary: "#fb923c"
  primary-bright: "#fca55f"
  primary-deep: "#f87c1c"
  on-primary: "#ffffff"
  ink: "#374151"
  ink-soft: "#6b7280"
  on-ink: "#ffffff"
  canvas: "#ffffff"
  paper: "#ffffff"
  cloud: "#ffffff"
  hairline: "#e5e7eb"
  surface-feature: "#1f2937"
  surface-deep: "#000000"
  link: "#374151"
  link-pressed: "#111827"
typography:
  display-xl: { fontFamily: "Sora", fontSize: 60px, fontWeight: 700, lineHeight: 1.1 }
  display-lg: { fontFamily: "Sora", fontSize: 48px, fontWeight: 600, lineHeight: 1.15 }
  display-md: { fontFamily: "Sora", fontSize: 36px, fontWeight: 600, lineHeight: 1.2 }
  heading-md: { fontFamily: "Sora", fontSize: 30px, fontWeight: 600, lineHeight: 1.25 }
  body-lg: { fontFamily: "Inter", fontSize: 20px, fontWeight: 500, lineHeight: 1.5 }
  body-md: { fontFamily: "Inter", fontSize: 16px, fontWeight: 400, lineHeight: 1.6 }
  link-md: { fontFamily: "Inter", fontSize: 14px, fontWeight: 500, lineHeight: 1.5 }
  button-lg: { fontFamily: "Inter", fontSize: 16px, fontWeight: 700, lineHeight: 1.5 }
  button-md: { fontFamily: "Inter", fontSize: 14px, fontWeight: 600, lineHeight: 1.5 }
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 10px
  xl: 24px
  pill: 9999px
spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section-md: 80px
  section-lg: 128px
shadows:
  none: "none"
  soft-lift: "rgba(0, 0, 0, 0.1) 0px 1px 3px 0px, rgba(0, 0, 0, 0.1) 0px 1px 2px -1px"
  card: "rgba(0, 0, 0, 0.1) 0px 4px 6px -1px, rgba(0, 0, 0, 0.1) 0px 2px 4px -2px"
  interactive: "rgba(0, 0, 0, 0.1) 0px 10px 15px -3px, rgba(0, 0, 0, 0.1) 0px 4px 6px -4px"
  modal: "rgba(0, 0, 0, 0.25) 0px 25px 50px -12px"
motion:
  duration-fast: "150ms"
  duration-base: "300ms"
  duration-slow: "500ms"
  ease-standard: "cubic-bezier(0.4, 0, 0.2, 1)"
  ease-emphasized: "cubic-bezier(0, 0, 0.2, 1)"
  transition-default: "all 150ms cubic-bezier(0.4, 0, 0.2, 1)"
  transition-transform: "transform 300ms cubic-bezier(0.4, 0, 0.2, 1)"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    color: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    padding: "{spacing.md} {spacing.xl}"
    typography: "{typography.button-lg}"
    shadow: "{shadows.interactive}"
    cursor: "pointer"
  button-primary-hover:
    transform: "translateY(-2px)"
    shadow: "{shadows.modal}"
  button-nav:
    backgroundColor: "{colors.primary}"
    color: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.lg}"
    typography: "{typography.button-md}"
    shadow: "{shadows.none}"
    cursor: "pointer"
  button-nav-hover:
    backgroundColor: "{colors.primary-bright}"
  card-feature:
    backgroundColor: "{colors.surface-feature}"
    color: "{colors.on-ink}"
    rounded: "{rounded.xl}"
    padding: "{spacing.xxl} {spacing.lg}"
    shadow: "{shadows.card}"
  navigation-link:
    color: "{colors.link}"
    typography: "{typography.link-md}"
    padding: "{spacing.xs} {spacing.sm}"
    cursor: "pointer"
  navigation-link-hover:
    color: "{colors.primary}"
  accordion-item:
    backgroundColor: "{colors.paper}"
    padding: "{spacing.lg}"
    borderBottom: "1px solid {colors.hairline}"
    cursor: "pointer"
```

## Visual Theme & Atmosphere

The PostGlee visual theme is modern, clean, and exceptionally user-friendly. It projects an atmosphere of simplicity and efficiency, assuring users that a complex task—social media management—is being made effortless. The design achieves this through a disciplined use of a minimal color palette, generous whitespace, and a clear typographic hierarchy. A vibrant, warm orange, `{colors.primary}`, serves as the energetic accent against a neutral backdrop of `{colors.canvas}` and `{colors.ink}`, creating focal points that guide the user without overwhelming them. The overall feeling is one of approachability, confidence, and streamlined productivity.

The visual language feels both professional and playful. The geometric shapes of the `Sora` heading font lend a contemporary, tech-forward feel, while the high readability of the `Inter` body font ensures clarity. Softly rounded corners on buttons (`{rounded.pill}`) and cards (`{rounded.xl}`) contribute to the friendly, accessible aesthetic, removing any sense of harshness or rigidity. Interactive elements provide satisfying, subtle feedback through motion and shadow, enhancing the sense of a polished, responsive tool.

**Key Characteristics:**
*   **Vibrant Accent:** A singular, bold accent color, `{colors.primary}`, is used with extreme discipline for primary calls-to-action and key textual highlights.
*   **High-Contrast Minimalism:** The palette is dominated by `{colors.canvas}`, `{colors.ink}`, and `{colors.surface-deep}`, creating a clean, high-contrast reading experience.
*   **Dual-Font Personality:** Headings use the geometric and stylish `Sora` font, as seen in `{typography.display-xl}`, while all body and UI text uses the highly legible and neutral `Inter` font, like `{typography.body-md}`.
*   **Generous Breathing Room:** The layout is governed by a generous spacing scale, with large gaps like `{spacing.section-md}` separating content blocks to reduce cognitive load.
*   **Softly Rounded Forms:** UI elements feature significant rounding, from the `{rounded.pill}` buttons to the `{rounded.xl}` feature cards, fostering a soft and approachable feel.
*   **Immersive Feature Sections:** Key features are presented in full-bleed sections with dark, gradient backgrounds starting from `{colors.surface-feature}`, creating distinct, focused zones with light `{colors.on-ink}` text.
*   **Subtle Elevation:** Depth is created through a consistent shadow system, from the gentle `{shadows.card}` to the more pronounced `{shadows.interactive}` on primary buttons, adding tactility without clutter.

## Color Usage Rules

The PostGlee color system is built on a deliberately small and highly functional palette. All new UI components must be composed from this core set to maintain brand consistency and visual clarity. The primary working colors are `{colors.primary}` (orange accent), `{colors.ink}` (dark text), `{colors.canvas}` (white background), and `{colors.surface-deep}` (black footer). Reusing these tokens is paramount; inventing new colors is forbidden.

*   **Primary (`{colors.primary}`):** This is the brand's signature orange. Its use must be strategic and limited. Use it exclusively for primary call-to-action buttons (e.g., "Start For Free"), critical navigation items ("Sign In"), and occasional, highly important text highlights. A single screen should ideally feature no more than two or three instances of `{colors.primary}` to preserve its impact. Never use it for body text or large background surfaces.

*   **Ink (`{colors.ink}` & `{colors.ink-soft}`):** `{colors.ink}` is the default color for all text, including headings and body copy, on light backgrounds. For secondary or less important text where a lighter feel is needed, use `{colors.ink-soft}` or reduce the font weight.

*   **On-Ink (`{colors.on-ink}`):** This pure white is reserved for all text and icons that appear on dark backgrounds, such as the feature cards (`{colors.surface-feature}`) or the deep footer (`{colors.surface-deep}`).

*   **Canvas, Paper, & Cloud (`{colors.canvas}`, `{colors.paper}`, `{colors.cloud}`):** `{colors.canvas}` is the primary background color for the entire page. `{colors.paper}` is used for any layered surfaces on top of the canvas that share the same color, such as the individual items in the FAQ section. As there are no alternating light-colored bands, `{colors.cloud}` defaults to the same white. The hero section features a subtle grid pattern using `{colors.hairline}` over `{colors.canvas}`.

*   **Feature & Deep Surfaces (`{colors.surface-feature}`, `{colors.surface-deep}`):** To create immersive, focused sections, use full-bleed backgrounds. The final site footer uses the solid `{colors.surface-deep}`. The main feature sections use complex gradients that start from a base close to `{colors.surface-feature}` and transition into other dark hues (indigo, green, etc.). When building these, start with `{colors.surface-feature}` as the base and apply a gradient overlay. Text on these surfaces must always be `{colors.on-ink}`.

*   **Hairline (`{colors.hairline}`):** Use this light gray for subtle, non-obtrusive dividers between elements, such as the bottom border on `{components.accordion-item}` or the background grid in the hero.

*   **Rule of Thumb:** Always ask if an existing token can serve the purpose before considering a new style. Emphasis and hierarchy should primarily be achieved through typography (`{typography.*}` tokens) and spacing (`{spacing.*}` tokens), not by introducing new colors.

## Typography Hierarchy

PostGlee employs a two-font strategy to create a clear visual hierarchy and brand personality. All headings and display text must use the **Sora** font family for its modern, geometric character. All body copy, paragraph text, and UI control labels must use the **Inter** font family for its exceptional readability at all sizes. This separation is strict and is a cornerstone of the brand's identity.

The typographic scale is designed for clarity and impact, ranging from the commanding `{typography.display-xl}` for hero headlines to the legible `{typography.body-md}` for detailed descriptions.

| Role | Token | Use |
| --- | --- | --- |
| Display XL | `{typography.display-xl}` | The main H1 headline for a page, as seen in the hero section. Use once per page. |
| Display LG | `{typography.display-lg}` | Major section titles that introduce a new, significant part of the page flow. |
| Display MD | `{typography.display-md}` | Substantial headings, such as the "Ready to simplify?" CTA block title. |
| Heading MD | `{typography.heading-md}` | Titles for components like feature cards or the FAQ section header. |
| Body LG | `{typography.body-lg}` | Sub-headlines or introductory paragraphs that support a major heading. |
| Body MD | `{typography.body-md}` | The default size for all paragraph text, descriptions within components, and FAQ questions. |
| Link MD | `{typography.link-md}` | Used for all text-based navigation links, such as in the main header and footer. |
| Button LG | `{typography.button-lg}` | The label for large, primary call-to-action buttons. |
| Button MD | `{typography.button-md}` | The label for smaller buttons, such as the "Sign In" button in the navigation. |

**Typography Principles:**
1.  **Strict Role Adherence:** Never use `Sora` for body copy or `Inter` for headings. The font choice is tied directly to the semantic role of the text.
2.  **Clear Hierarchy:** Use the defined typographic scale to guide the user's eye. A larger font size and heavier weight always signify greater importance.
3.  **Optimize for Readability:** Body text is always set in `{typography.body-md}` with a generous line height of 1.6 to ensure comfortable reading, especially for longer passages.
4.  **Expressive Headlines:** Use the `Sora` font's inherent style to make headlines engaging and memorable. The slightly condensed nature and geometric forms of `{typography.display-xl}` create immediate impact.
5.  **Consistency in Interaction:** All interactive text elements, like links and buttons, use the `Inter` font to create a consistent set of UI controls.

## Component Patterns

PostGlee's components are designed to be clean, reusable, and intuitive. They combine tokens from color, typography, and spacing to create a cohesive user experience. All interactive components provide clear visual feedback.

**Primary Button (`button-primary`)**
This is the most prominent call-to-action button, reserved for the single most important action on a page, like "Start For Free". It uses the brand's `{colors.primary}` for its background, with `{colors.on-primary}` text set in `{typography.button-lg}`. Its `{rounded.pill}` shape makes it friendly and distinct. It carries a `{shadows.interactive}` to lift it off the page. On hover, it has a subtle lift effect achieved with `transform: translateY(-2px)` and an enhanced `{shadows.modal}`, animated over `{motion.transition-default}`. It must always use `cursor: pointer`.

**Navigation Button (`button-nav`)**
This smaller button is used for secondary actions within the main site navigation, like "Sign In". It shares the `{colors.primary}` background and `{rounded.pill}` shape but is more demure, with smaller `{typography.button-md}` text and `{shadows.none}`. On hover, the background color transitions to `{colors.primary-bright}` over `{motion.duration-fast}`. It must always use `cursor: pointer`.

**Feature Card (`card-feature`)**
These cards are the primary vehicle for explaining product benefits. They are visually rich, using a dark background specified by `{colors.surface-feature}` which serves as a base for colorful gradients. The large `{rounded.xl}` radius and generous internal padding (`{spacing.xxl} {spacing.lg}`) give content ample room to breathe. All text within the card must be `{colors.on-ink}` to ensure high contrast and readability. These cards have a subtle `{shadows.card}` to distinguish them from the page background.

**Navigation Link (`navigation-link`)**
These are standard text links used in the header and footer. They use `{colors.link}` text set in `{typography.link-md}`. They are simple and unobtrusive. On hover, the text color smoothly transitions to `{colors.primary}` over `{motion.duration-fast}`. The clickable area is increased with padding of `{spacing.xs} {spacing.sm}`. It must always use `cursor: pointer`.

**Accordion Item (`accordion-item`)**
Used in the FAQ section, this component presents a question that can be clicked to reveal an answer. The container has a `{colors.paper}` background and is separated from its neighbors by a `1px solid {colors.hairline}` border. The entire item is interactive and must use `cursor: pointer`. The question text uses `{typography.body-md}`. The expansion and collapse of the answer panel should be animated.

## Backend HTML & Email Template Guidelines (`templates/**/*.html`)

When creating or modifying server-rendered Django templates (e.g. `templates/oauth2_provider/authorize.html`) or email templates (`templates/emails/*.html`):

1. **Always Include Google Fonts (`Sora` & `Inter`):**
   ```html
   <link rel="preconnect" href="https://fonts.googleapis.com">
   <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
   <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700&display=swap" rel="stylesheet">
   ```
2. **Use the Official PostGlee Logo with Text Fallback:**
   ```html
   <img src="https://postglee.com/postglee-logo.png" alt="PostGlee" class="logo-img" width="148" height="38" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-block';" />
   <span class="logo-fallback" style="display: none;">PostGlee</span>
   ```
3. **Buttons & Cards:**
   - Primary buttons use `background-color: #fb923c`, `color: #ffffff`, and pill radius (`border-radius: 9999px`).
   - Cards use `#ffffff` (`paper`), `1px solid #e5e7eb` (`hairline`), rounded corners (`24px` for standalone web cards, `16px` for email containers), and balanced `32px` padding.
4. **Reference Existing Templates First:**
   - Before writing any new template, inspect `templates/oauth2_provider/authorize.html` and `templates/emails/post_status.html` to keep spacing, header, footer, and button styles 100% consistent.

## Layout & Spacing

The layout of PostGlee is built on a foundation of generous whitespace and a consistent, rhythmic spacing scale. This creates a calm, uncluttered interface that is easy to scan and digest. The core of the system is a base unit from which all spacing values are derived, promoting harmony and predictability across the entire UI.

The primary spacing rhythm is built on a 4px grid, with tokens like `{spacing.xxs}` (4px), `{spacing.xs}` (8px), `{spacing.md}` (16px), and `{spacing.xl}` (32px) used for padding, margins, and gaps between elements. This scale must be strictly adhered to; arbitrary pixel values are not permitted.

## Do's and Don'ts

**Do's:**
1.  **Do** strictly adhere to the two-font system: `Sora` for all headings, `Inter` for all body and UI text.
2.  **Do** build all layouts using the defined `{spacing.*}` tokens for padding, margins, and gaps to maintain a consistent rhythm.
3.  **Do** compose all new UI from the existing core color palette, primarily `{colors.primary}`, `{colors.ink}`, and `{colors.canvas}`.
4.  **Do** reserve `{colors.primary}` for the most important calls-to-action and key highlights to maintain its visual power.
5.  **Do** use the `{shadows.*}` tokens to create a consistent sense of elevation and interactivity.
6.  **Do** ensure every interactive element (buttons, links, accordions) uses `cursor: pointer` to provide clear affordance.
7.  **Do** ensure all text has sufficient contrast, using `{colors.ink}` on `{colors.canvas}` and `{colors.on-ink}` on dark surfaces.

**Don'ts:**
1.  **Don't** ever use a color that is not defined in the `{colors.*}` token set. Reuse existing tokens.
2.  **Don't** ever add a `box-shadow` that does not map to a `{shadows.*}` token. The elevation system is intentional.
3.  **Don't** ever leave the browser-default arrow cursor on a clickable element. Every interactive element must set its cursor property.
4.  **Don't** mix the `Sora` and `Inter` fonts outside of their designated heading/body roles.
5.  **Don't** use arbitrary pixel values for spacing or sizing. Always reference a `{spacing.*}` or `{rounded.*}` token.
6.  **Don't** overuse `{colors.primary}`. It is an accent color, not a primary surface color.
7.  **Don't** set body copy in any style other than `{typography.body-md}` or `{typography.body-lg}` to maintain readability.
8.  **Don't** forget to apply hover and focus states to all interactive components using the `{motion.*}` tokens for smooth transitions.
