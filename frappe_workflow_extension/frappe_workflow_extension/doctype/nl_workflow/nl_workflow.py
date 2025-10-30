import frappe
from frappe import _
from frappe.model.document import Document


class NLWorkflow(Document):
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from frappe.workflow.doctype.workflow_document_state.workflow_document_state import (
            WorkflowDocumentState,
        )
        from frappe.workflow.doctype.workflow_transition.workflow_transition import (
            WorkflowTransition,
        )

        document_type: DF.Link
        is_active: DF.Check
        override_status: DF.Check
        send_email_alert: DF.Check
        states: DF.Table[WorkflowDocumentState]
        transitions: DF.Table[WorkflowTransition]
        workflow_data: DF.JSON | None
        workflow_name: DF.Data
        workflow_state_field: DF.Data
        user: DF.Link | None
        company: DF.Link | None
        project: DF.Link | None

    def validate(self):
        # self.set_active()
        self.validate_docstatus()
        self.validate_unique_active_combination()

    def on_update(self):
        self.create_custom_field_for_workflow_state()
        self.update_default_workflow_status()

    def create_custom_field_for_workflow_state(self):
        frappe.clear_cache(doctype=self.document_type)
        meta = frappe.get_meta(self.document_type)

        if not meta.get_field(self.workflow_state_field):
            custom_field = frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": self.document_type,
                    "fieldname": self.workflow_state_field,
                    "label": self.workflow_state_field.replace("_", " ").title(),
                    "hidden": 1,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "fieldtype": "Link",
                    "options": "Workflow State",
                    "owner": "Administrator",
                }
            )
            custom_field.insert(ignore_permissions=True)
            frappe.msgprint(
                _("Created Custom Field {0} in {1}").format(
                    self.workflow_state_field, self.document_type
                )
            )

    def update_default_workflow_status(self):
        states = self.get("states") or []
        if not states:
            return

        for d in states:
            docs_to_update = frappe.get_all(
                self.document_type,
                filters={
                    self.workflow_state_field: ["in", ["", None]],
                    "docstatus": d.doc_status,
                },
                pluck="name",
            )

            for name in docs_to_update:
                frappe.db.set_value(
                    self.document_type, name, self.workflow_state_field, d.state
                )

    def validate_docstatus(self):
        def get_state(state):
            for s in self.states:
                if s.state == state:
                    return s
            frappe.throw(_("{0} is not a valid State").format(state))

        for t in self.transitions:
            state = get_state(t.state)
            next_state = get_state(t.next_state)

            if state.doc_status == "2":
                frappe.throw(
                    _(
                        "Cannot change state of Cancelled Document (Transition row {0})"
                    ).format(t.idx)
                )

            if state.doc_status == "1" and next_state.doc_status == "0":
                frappe.throw(
                    _(
                        "Submitted Document cannot revert to Draft (Transition row {0})"
                    ).format(t.idx)
                )

            if state.doc_status == "0" and next_state.doc_status == "2":
                frappe.throw(
                    _("Cannot cancel before submitting (Transition row {0})").format(
                        t.idx
                    )
                )

    def set_active(self):
        """Deactivate other workflows for the same document type if this one is active."""
        if int(self.is_active or 0):
            other_workflows = frappe.get_all(
                "NL Workflow",
                filters={
                    "document_type": self.document_type,
                    "is_active": 1,
                    "name": ["!=", self.name],
                },
                pluck="name",
            )
            for wf in other_workflows:
                frappe.db.set_value("NL Workflow", wf, "is_active", 0)

    def validate_unique_active_combination(self):
        """Ensure only one active workflow exists per unique combination of
        document_type, company, project, and user."""
        if not self.document_type:
            frappe.throw(_("Document Type is required for workflow validation."))

        if not self.is_active:
            return

        filters = {
            "document_type": self.document_type,
            "is_active": 1,
            "name": ["!=", self.name],
        }

        if self.company:
            filters["company"] = self.company
        if self.project:
            filters["project"] = self.project
        if self.user:
            filters["user"] = self.user

        existing = frappe.get_all(
            "NL Workflow",
            filters=filters,
            fields=["name", "company", "project", "user"],
        )

        if existing:
            existing_doc = existing[0]

            reason_parts = []
            if existing_doc.company:
                reason_parts.append(_("Company '{0}'").format(existing_doc.company))
            if existing_doc.project:
                reason_parts.append(_("Project '{0}'").format(existing_doc.project))
            if existing_doc.user:
                reason_parts.append(_("User '{0}'").format(existing_doc.user))

            if not reason_parts:
                reason_text = _("This is a global workflow for the same Document Type.")
            else:
                reason_text = _("It matches the same ") + ", ".join(reason_parts)

            frappe.throw(
                _(
                    "Duplicate Active Workflow Detected: The workflow '{0}' is already active for Document Type '{1}'. {2} "
                    "Only one active workflow is allowed per unique combination of Document Type, Company, Project, and User."
                ).format(existing_doc.name, self.document_type, reason_text)
            )


@frappe.whitelist()
def get_workflow_state_count(doctype, workflow_state_field, states):
    frappe.has_permission(doctype=doctype, ptype="read", throw=True)
    states = frappe.parse_json(states)

    if workflow_state_field in frappe.get_meta(doctype).get_valid_columns():
        result = (
            frappe.qb.from_(frappe.qb.DocType(doctype))
            .select(
                frappe.qb.Field(workflow_state_field),
                frappe.qb.functions.Count("*").as_("count"),
            )
            .where(frappe.qb.Field(workflow_state_field).notin(states))
            .groupby(frappe.qb.Field(workflow_state_field))
        ).run(as_dict=True)

        return [r for r in result if r.get(workflow_state_field)]
