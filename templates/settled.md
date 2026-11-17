# Design questions settled during planning

Each row records a question that the area plans left open and that the rules, the maps, production behaviour or an earlier answer decided. A question that none of them decides is not here: it goes to the developer (`track ask`, and in chat).

Ids: `S-<area letter><question number>`. Conflict resolutions that were not open questions belong in the conflicts file.

## <area>

| Id | Question | Settled | Reason |
|---|---|---|---|
| S-X1 | How the app's canvas tools reach the app while the tool host holds the selected tool. | (a) The host wraps the app for one pass and each tool borrows it for one method call. | Production runs press-time picks in the same pass; (b) would delay them a pass and give every tool family its own queue. |
| S-X2 | Menu zoom anchor. | (a) Zoom about the centre, as the menu bar and the shortcuts do. Recorded as a difference from production. | One view-command path (one mechanism per concept); product detail is not asked during the port. |
| S-X3 | Mouse wheel over an unfocused number field. | (a) The framework's rule: the field takes the wheel. | Every field behaves the same way; an app exception would need a second mechanism. |
