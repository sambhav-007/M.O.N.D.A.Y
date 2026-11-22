# M.O.N.D.A.Y. community roadmap

This roadmap is a set of proposed priorities, not a delivery schedule. The
project is open to feedback on what would make M.O.N.D.A.Y. more reliable,
understandable, and useful to contributors and users.

## Current public-launch priorities

- Make first-time Windows setup clear and repeatable.
- Expand the real product screenshots and publish an introductory walkthrough
  video.
- Keep product, engineering, and academic documentation distinct and current.
- State security, privacy, and known capability limits plainly.
- Establish contributor guidance and keep the offline test suite dependable.
- Choose and publish a repository license before inviting reuse or
  redistribution.

## Proposed next areas

### Reliability and packaging

- Improve startup diagnostics and supported-environment guidance.
- Explore a versioned Windows package after the setup path is stable.
- Make optional integrations fail clearly when they are not configured.

### Voice and accessibility

- Improve voice availability and recovery across supported Windows browsers.
- Continue refining keyboard control, visible state, and readable responses.
- Document which speech paths require a network connection.

### Skills and integrations

- Add integrations only when their permissions, data flow, and failure modes
  can be explained and tested.
- Keep irreversible operations behind explicit approval.
- Prefer local processing when it fits the task and user expectations.

### Developer experience

- Make agent and skill extension points easier to understand.
- Keep examples and API documentation aligned with the running implementation.
- Welcome small, testable contributions before expanding scope.

## Help shape the roadmap

Open a [GitHub issue](https://github.com/sambhav-007/M.O.N.D.A.Y/issues) with a
clear problem statement, the user who benefits, and an example of the expected
behavior. For larger changes, discuss the approach before writing a large
implementation.

The detailed, environment-specific implementation plan is preserved in
[ROADMAP_ENGINEERING.md](ROADMAP_ENGINEERING.md).
