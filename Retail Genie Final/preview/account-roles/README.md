# Account-role access previews

Captured at 1440 × 1000 from the local Flask preview using disposable synthetic data. Each image shows the signed-in role's dashboard and expanded navigation. The additional settings images show manager access and the super-admin company picker. No live or production data was used; these images are not live-MySQL validation.

| Account type | Screenshot |
|---|---|
| Super admin | [Dashboard and navigation](super-admin.png) · [Settings company picker](super-admin-settings-company-picker.png) |
| Company admin | [Dashboard and navigation](company-admin.png) |
| Admin | [Dashboard and navigation](admin.png) |
| Manager | [Dashboard and navigation](manager.png) · [Company settings](manager-settings.png) |
| Salesperson | [Dashboard and navigation](salesperson.png) |
| Storekeeper | [Dashboard and navigation](storekeeper.png) |
| Cashier | [Dashboard and navigation](cashier.png) |
| Logistics | [Dashboard and navigation](logistics.png) |
| Auditor | [Dashboard and navigation](auditor.png) |
| Display | [Dashboard and navigation](display.png) |
| Express | [Dashboard and navigation](express.png) |

The broader isolated role-access audit covered **11 roles** and **72 permissions**. All **1,584** role/permission grant assertions passed. The updated dashboard rendered **166 function links** across the 11 roles; none returned HTTP 401 or 403 when opened by the role that was shown them. A route/method smoke made **2,057 calls** (187 non-auth route methods × 11 roles) with no 401s, unexpected exceptions, or 5xx responses; role-specific 403s were expected for functions outside a role's authorization. Role-specific landing pages were also opened successfully for all 11 account types. The compatible application test suite passed (**147 passed, 1 interactive CLI test deselected**). All checks used isolated SQLite fixtures; this does not count as live-MySQL validation, and empty-payload route smoke checks do not replace full business-flow validation for every mutation.
