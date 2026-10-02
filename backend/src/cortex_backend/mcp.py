"""FastMCP registry composition."""

from datetime import date, datetime

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from .api.mcp import database_storage, get_mcp_auth
from .attachments.errors import AttachmentError
from .embeddings.provider import EmbeddingProvider
from .files.errors import FileError
from .files.schemas import (
    FileContextResponse,
    FileContextStatus,
    FileListResponse,
    FileResponse,
    FileUpdateRequest,
)
from .files.service import (
    DEFAULT_CONTEXT_CHARACTERS,
    MAX_CONTEXT_CHARACTERS,
    FileListFilters,
    FileRecord,
    delete_file,
    get_file,
    get_file_context,
    list_files,
    restore_file,
    update_file,
)
from .files.storage import FileBlobStore
from .grounding.errors import GroundingError
from .grounding.schemas import GroundedCitationResponse, GroundedQuestionResponse
from .grounding.service import GroundedQuestionPackage
from .grounding.service import prepare_question as prepare_grounded_question
from .logs.errors import ActivityLogError
from .logs.schemas import (
    ActivityLogCreateRequest,
    ActivityLogListResponse,
    ActivityLogResponse,
)
from .logs.service import ActivityLogFilters, ActivityLogRecord, append_log, list_logs
from .memory.errors import NoteError
from .memory.schemas import NoteCreateRequest, NoteListResponse, NoteResponse, NoteUpdateRequest
from .memory.service import (
    NoteListFilters,
    NoteRecord,
    create_note,
    delete_note,
    get_note,
    list_notes,
    restore_note,
    update_note,
)
from .money.errors import MoneyError
from .money.schemas import (
    AccountCreateRequest,
    AccountListResponse,
    AccountResponse,
    AccountUpdateRequest,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpsertRequest,
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdateRequest,
    InstallmentOccurrenceResponse,
    InstallmentPlanCreateRequest,
    InstallmentPlanListResponse,
    InstallmentPlanResponse,
    InstallmentPlanState,
    InstallmentProcessResponse,
    MoneyRecurrenceRequest,
    MoneyRecurrenceState,
    MoneySummaryResponse,
    PayeeCreateRequest,
    PayeeListResponse,
    PayeeResponse,
    PayeeUpdateRequest,
    PostingResponse,
    ReconciliationState,
    RecurringOccurrenceResponse,
    RecurringPostingResponse,
    RecurringProcessResponse,
    RecurringTransactionCreateRequest,
    RecurringTransactionListResponse,
    RecurringTransactionResponse,
    RecurringTransactionUpdateRequest,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
    TransactionReverseRequest,
    TransactionState,
    TransactionUpdateRequest,
)
from .money.service import (
    AccountListFilters,
    AccountRecord,
    BudgetListFilters,
    BudgetRecord,
    CategoryListFilters,
    CategoryRecord,
    InstallmentPlanListFilters,
    InstallmentPlanRecord,
    MoneySummaryRecord,
    PayeeListFilters,
    PayeeRecord,
    RecurringTransactionListFilters,
    RecurringTransactionRecord,
    TransactionListFilters,
    TransactionRecord,
    archive_account,
    archive_category,
    archive_payee,
    cancel_installment_plan,
    clear_posting,
    create_account,
    create_category,
    create_installment_plan,
    create_payee,
    create_recurring_transaction,
    create_transaction,
    delete_budget,
    end_recurring_transaction,
    get_account,
    get_budget,
    get_category,
    get_installment_plan,
    get_money_summary,
    get_payee,
    get_recurring_transaction,
    get_transaction,
    list_accounts,
    list_budgets,
    list_categories,
    list_installment_plans,
    list_payees,
    list_recurring_transactions,
    list_transactions,
    pause_recurring_transaction,
    process_due_installments,
    process_due_recurring_transactions,
    reconcile_posting,
    restore_account,
    restore_category,
    restore_payee,
    restore_transaction,
    resume_recurring_transaction,
    reverse_transaction,
    update_account,
    update_category,
    update_payee,
    update_recurring_transaction,
    update_transaction,
    upsert_budget,
    void_transaction,
)
from .recovery.errors import RecoveryError
from .recovery.schemas import (
    RecoveryBatchRequest,
    RecoveryItemResponse,
    RecoveryListResponse,
    RecoveryMutationResponse,
)
from .recovery.service import RecoveryListFilters, list_recovery_items, mutate_recovery_items
from .storage import Storage
from .tags.errors import TagError
from .tags.schemas import TagListResponse, TagResponse
from .tags.service import list_tags
from .tasks.errors import TaskError
from .tasks.schemas import (
    RecurrenceState,
    TaskCreateRequest,
    TaskListOrder,
    TaskListResponse,
    TaskPriority,
    TaskRecurrenceRequest,
    TaskReorderRequest,
    TaskResponse,
    TaskSeriesListResponse,
    TaskSeriesResponse,
    TaskSeriesUpdateRequest,
    TaskStatus,
    TaskSummaryResponse,
    TaskTagSummaryResponse,
    TaskUpdateRequest,
)
from .tasks.service import (
    TaskListFilters,
    TaskRecord,
    TaskSeriesRecord,
    create_task,
    delete_task,
    end_task_series,
    get_task,
    get_task_series,
    list_task_series,
    list_tasks,
    pause_task_series,
    reorder_task,
    resume_task_series,
    skip_task_occurrence,
    summarize_tasks,
    update_task,
    update_task_series,
)


def _response(record: TaskRecord) -> TaskResponse:
    return TaskResponse(
        id=record.id,
        title=record.title,
        description=record.description,
        status=record.status,
        priority=record.priority,
        position=record.position,
        start_at=record.start_at,
        due_at=record.due_at,
        tags=record.tags,
        attachments=[_file_response(file) for file in record.attachments],
        created_at=record.created_at,
        updated_at=record.updated_at,
        series_id=record.series_id,
        occurrence_key=record.occurrence_key,
        series_exception=record.series_exception,
        skipped_at=record.skipped_at,
    )


def _series_response(record: TaskSeriesRecord) -> TaskSeriesResponse:
    return TaskSeriesResponse(
        id=record.id,
        state=RecurrenceState(record.state),
        title=record.title,
        description=record.description,
        status=record.status,
        priority=record.priority,
        tags=record.tags,
        attachments=[_file_response(file) for file in record.attachments],
        recurrence=TaskRecurrenceRequest.model_validate(
            {
                "timezone": record.timezone,
                "frequency": record.frequency,
                "interval": record.interval,
                "weekdays": record.weekdays,
                "month_day": record.month_day,
                "month": record.month,
                "day": record.day,
                "until_date": record.until_date,
                "occurrence_count": record.occurrence_count,
            }
        ),
        materialized_through_at=record.materialized_through_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _raise_tool(error: TaskError | NoteError | TagError | AttachmentError) -> None:
    details = ""
    if hasattr(error, "unknown_tags") and hasattr(error, "allowed_tags"):
        details = f" Unknown tags: {error.unknown_tags}. Allowed tags: {error.allowed_tags}."
    raise ToolError(f"{error.code}: {error.message}{details}") from error


def _activity_log_response(record: ActivityLogRecord) -> ActivityLogResponse:
    return ActivityLogResponse(
        id=record.id,
        user_id=record.user_id,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        metadata=record.metadata,
        created_at=record.created_at,
    )


def _raise_activity_log_tool(error: ActivityLogError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _file_response(record: FileRecord) -> FileResponse:
    return FileResponse(
        id=record.id,
        name=record.name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        tags=record.tags,
        context_status=record.context_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _raise_file_tool(error: FileError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _note_response(record: NoteRecord) -> NoteResponse:
    return NoteResponse(
        id=record.id,
        title=record.title,
        body=record.body,
        journal_date=record.journal_date,
        tags=record.tags,
        attachments=[_file_response(file) for file in record.attachments],
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _raise_note_tool(error: NoteError | TagError | AttachmentError) -> None:
    _raise_tool(error)


def _raise_recovery_tool(error: RecoveryError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _grounded_question_response(package: GroundedQuestionPackage) -> GroundedQuestionResponse:
    return GroundedQuestionResponse(
        question=package.question,
        prompt=package.prompt,
        context_text=package.context_text,
        citations=[
            GroundedCitationResponse(
                citation=passage.citation,
                text=passage.text,
                chunk_id=passage.chunk_id,
                source_type=passage.source_type,
                source_id=passage.source_id,
                source_name=passage.source_name,
                source_version=passage.source_version,
                chunk_ordinal=passage.chunk_ordinal,
                retrieval_rank=passage.retrieval_rank,
                retrieval_score=passage.retrieval_score,
                file_ids=list(passage.file_ids),
                file_names=list(passage.file_names),
            )
            for passage in package.citations
        ],
        has_context=package.has_context,
        empty_reason=package.empty_reason,
        message=package.message,
    )


def _raise_grounding_tool(error: GroundingError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _raise_money_tool(error: MoneyError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _money_account_response(record: AccountRecord) -> AccountResponse:
    return AccountResponse(
        id=record.id,
        name=record.name,
        account_type=record.account_type,
        institution_name=record.institution_name,
        last_four=record.last_four,
        currency_code=record.currency_code,
        opening_balance=record.opening_balance,
        balance=record.balance,
        credit_limit=record.credit_limit,
        amount_owed=record.amount_owed,
        available_credit=record.available_credit,
        statement_close_day=record.statement_close_day,
        payment_due_day=record.payment_due_day,
        next_statement_close_date=record.next_statement_close_date,
        next_payment_due_date=record.next_payment_due_date,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _money_payee_response(record: PayeeRecord) -> PayeeResponse:
    return PayeeResponse(
        id=record.id,
        name=record.name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _money_category_response(record: CategoryRecord) -> CategoryResponse:
    return CategoryResponse(
        id=record.id,
        name=record.name,
        kind=record.kind,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _money_budget_response(record: BudgetRecord) -> BudgetResponse:
    return BudgetResponse(
        id=record.id,
        category_id=record.category_id,
        period=record.period,
        currency_code=record.currency_code,
        amount=record.amount,
        spent_amount=record.spent_amount,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _money_summary_response(record: MoneySummaryRecord) -> MoneySummaryResponse:
    return MoneySummaryResponse(
        period=record.period,
        currency_code=record.currency_code,
        total_balance=record.total_balance,
        income_amount=record.income_amount,
        spending_amount=record.spending_amount,
        budget_amount=record.budget_amount,
        budget_spent_amount=record.budget_spent_amount,
        budget_remaining_amount=record.budget_remaining_amount,
    )


def _money_transaction_response(record: TransactionRecord) -> TransactionResponse:
    return TransactionResponse(
        id=record.id,
        transaction_date=record.transaction_date,
        name=record.name,
        payee_id=record.payee_id,
        memo=record.memo,
        state=TransactionState(record.state),
        reversal_of_id=record.reversal_of_id,
        postings=[
            PostingResponse(
                id=posting.id,
                position=posting.position,
                label=posting.label,
                account_id=posting.account_id,
                category_id=posting.category_id,
                currency_code=posting.currency_code,
                amount=posting.amount,
                reconciliation_state=posting.reconciliation_state,
                cleared_at=posting.cleared_at,
                reconciled_at=posting.reconciled_at,
            )
            for posting in record.postings
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
        voided_at=record.voided_at,
        void_reason=record.void_reason,
    )


def _money_installment_plan_response(record: InstallmentPlanRecord) -> InstallmentPlanResponse:
    return InstallmentPlanResponse(
        id=record.id,
        account_id=record.account_id,
        payee_id=record.payee_id,
        category_id=record.category_id,
        currency_code=record.currency_code,
        purchase_date=record.purchase_date,
        name=record.name,
        memo=record.memo,
        total_amount=record.total_amount,
        fee_amount=record.fee_amount,
        term_months=record.term_months,
        status=record.status,
        charged_count=record.charged_count,
        next_charge_date=record.next_charge_date,
        next_charge_amount=record.next_charge_amount,
        remaining_amount=record.remaining_amount,
        occurrences=[
            InstallmentOccurrenceResponse(
                id=occurrence.id,
                sequence_number=occurrence.sequence_number,
                charge_date=occurrence.charge_date,
                amount=occurrence.amount,
                status=occurrence.status,
                transaction_id=occurrence.transaction_id,
                charged_at=occurrence.charged_at,
            )
            for occurrence in record.occurrences
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _money_recurring_transaction_response(
    record: RecurringTransactionRecord,
) -> RecurringTransactionResponse:
    return RecurringTransactionResponse(
        id=record.id,
        start_date=record.start_date,
        name=record.name,
        payee_id=record.payee_id,
        memo=record.memo,
        recurrence=MoneyRecurrenceRequest(
            timezone=record.timezone,
            frequency=record.frequency,
            interval=record.interval,
            weekdays=record.weekdays,
            month_day=record.month_day,
            month=record.month,
            day=record.day,
            until_date=record.until_date,
            occurrence_count=record.occurrence_count,
        ),
        state=record.state,
        next_occurrence_date=record.next_occurrence_date,
        next_occurrence_number=record.next_occurrence_number,
        posted_count=record.posted_count,
        postings=[
            RecurringPostingResponse(
                id=posting.id,
                account_id=posting.account_id,
                category_id=posting.category_id,
                currency_code=posting.currency_code,
                amount=posting.amount,
            )
            for posting in record.postings
        ],
        occurrences=[
            RecurringOccurrenceResponse(
                id=occurrence.id,
                sequence_number=occurrence.sequence_number,
                due_date=occurrence.due_date,
                status=occurrence.status,
                transaction_id=occurrence.transaction_id,
                processed_at=occurrence.processed_at,
            )
            for occurrence in record.occurrences
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
        paused_at=record.paused_at,
        ended_at=record.ended_at,
    )


def create_mcp_server(
    name: str = "Cortex",
    storage: Storage | None = None,
    file_storage: FileBlobStore | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> FastMCP:
    """Create the MCP registry backed by shared domain service functions."""

    server = FastMCP(name)

    @server.tool(name="prepare_question")
    async def prepare_question_tool(
        question: str, ctx: Context | None = None
    ) -> GroundedQuestionResponse:
        """Prepare owner-scoped context and a citation-grounded prompt for answering a question."""

        del ctx
        try:
            package = await prepare_grounded_question(
                database_storage(storage),
                get_mcp_auth().user.id,
                question,
                embedding_provider=embedding_provider,
            )
        except GroundingError as exc:
            _raise_grounding_tool(exc)
        return _grounded_question_response(package)

    @server.tool(name="list_recovery_items")
    async def list_recovery_items_tool(
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> RecoveryListResponse:
        """List deleted and archived records across the owner-scoped domains."""

        del ctx
        try:
            page = await list_recovery_items(
                database_storage(storage),
                get_mcp_auth().user.id,
                RecoveryListFilters(limit=limit, cursor=cursor),
            )
        except RecoveryError as exc:
            _raise_recovery_tool(exc)
        return RecoveryListResponse(
            items=[
                RecoveryItemResponse(
                    type=item.type,
                    id=item.id,
                    label=item.label,
                    removed_at=item.removed_at,
                    created_at=item.created_at,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="restore_recovery_items")
    async def restore_recovery_items_tool(
        payload: RecoveryBatchRequest,
        ctx: Context | None = None,
    ) -> RecoveryMutationResponse:
        """Restore one or more deleted or archived records."""

        del ctx
        results = await mutate_recovery_items(
            database_storage(storage),
            file_storage,
            get_mcp_auth().user.id,
            payload.items,
            permanent=False,
        )
        return RecoveryMutationResponse(results=results)

    @server.tool(name="permanently_delete_recovery_items")
    async def permanently_delete_recovery_items_tool(
        payload: RecoveryBatchRequest,
        ctx: Context | None = None,
    ) -> RecoveryMutationResponse:
        """Permanently delete one or more deleted or archived records."""

        del ctx
        results = await mutate_recovery_items(
            database_storage(storage),
            file_storage,
            get_mcp_auth().user.id,
            payload.items,
            permanent=True,
        )
        return RecoveryMutationResponse(results=results)

    @server.tool(name="list_tags")
    async def list_tags_tool(ctx: Context | None = None) -> TagListResponse:
        """List active shared tags for note, task, and file updates."""

        del ctx
        records = await list_tags(
            database_storage(storage),
            get_mcp_auth().user.id,
        )
        return TagListResponse(
            items=[
                TagResponse(
                    id=record.id,
                    name=record.name,
                    color=record.color,
                    active=record.active,
                    created_at=record.created_at,
                    archived_at=record.archived_at,
                )
                for record in records
            ]
        )

    @server.tool(name="list_files")
    async def list_files_tool(
        include_deleted: bool = False,
        tag: list[str] | None = None,
        search: str | None = None,
        context_status: list[FileContextStatus] | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> FileListResponse:
        """List owner-scoped file metadata without returning binary contents."""

        del ctx
        try:
            page = await list_files(
                database_storage(storage),
                get_mcp_auth().user.id,
                FileListFilters(
                    include_deleted=include_deleted,
                    tags=tuple(tag or ()),
                    search=search,
                    context_statuses=tuple(context_status or ()),
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except FileError as exc:
            _raise_file_tool(exc)
        return FileListResponse(
            items=[_file_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="update_file")
    async def update_file_tool(
        file_id: str,
        payload: FileUpdateRequest,
        ctx: Context,
    ) -> FileResponse:
        """Replace one active file's shared catalog tags."""

        del ctx
        try:
            record = await update_file(
                database_storage(storage),
                get_mcp_auth().user.id,
                file_id,
                payload,
            )
        except FileError as exc:
            _raise_file_tool(exc)
        except TagError as exc:
            _raise_tool(exc)
        return _file_response(record)

    @server.tool(name="get_file")
    async def get_file_tool(file_id: str, ctx: Context) -> FileResponse:
        """Return one active owner-scoped file's metadata."""

        del ctx
        try:
            record = await get_file(database_storage(storage), get_mcp_auth().user.id, file_id)
        except FileError as exc:
            _raise_file_tool(exc)
        return _file_response(record)

    @server.tool(name="get_file_context")
    async def get_file_context_tool(
        file_id: str,
        max_characters: int = DEFAULT_CONTEXT_CHARACTERS,
        ctx: Context | None = None,
    ) -> FileContextResponse:
        """Return bounded extracted context for one active source file."""

        del ctx
        if not 1 <= max_characters <= MAX_CONTEXT_CHARACTERS:
            raise ToolError("invalid_file_query: The file list query is invalid.")
        try:
            if file_storage is None:
                raise ToolError("file_storage_unavailable: File storage is not available.")
            record = await get_file_context(
                database_storage(storage),
                file_storage,
                get_mcp_auth().user.id,
                file_id,
                max_characters,
            )
        except FileError as exc:
            _raise_file_tool(exc)
        return FileContextResponse(
            file_id=record.file_id,
            name=record.name,
            status=record.status,
            text=record.text,
            truncated=record.truncated,
            preview_kind=record.preview_kind,
            error=record.error,
            processed_at=record.processed_at,
        )

    @server.tool(name="delete_file")
    async def delete_file_tool(file_id: str, ctx: Context) -> str:
        """Soft-delete one active owner-scoped file."""

        del ctx
        try:
            await delete_file(database_storage(storage), get_mcp_auth().user.id, file_id)
        except FileError as exc:
            _raise_file_tool(exc)
        return "File deleted."

    @server.tool(name="restore_file")
    async def restore_file_tool(file_id: str, ctx: Context) -> FileResponse:
        """Restore one owner-scoped file."""

        del ctx
        try:
            record = await restore_file(database_storage(storage), get_mcp_auth().user.id, file_id)
        except FileError as exc:
            _raise_file_tool(exc)
        return _file_response(record)

    @server.tool(name="create_money_account")
    async def create_money_account_tool(
        payload: AccountCreateRequest, ctx: Context | None = None
    ) -> AccountResponse:
        """Create an owner-scoped money account."""

        del ctx
        try:
            record = await create_account(
                database_storage(storage), get_mcp_auth().user.id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_account_response(record)

    @server.tool(name="list_money_accounts")
    async def list_money_accounts_tool(
        include_archived: bool = False,
        archived_only: bool = False,
        search: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> AccountListResponse:
        """List owner-scoped money accounts."""

        del ctx
        try:
            page = await list_accounts(
                database_storage(storage),
                get_mcp_auth().user.id,
                AccountListFilters(
                    include_archived=include_archived,
                    archived_only=archived_only,
                    search=search,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return AccountListResponse(
            items=[_money_account_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_account")
    async def get_money_account_tool(
        account_id: str, ctx: Context | None = None
    ) -> AccountResponse:
        """Return one owner-scoped money account."""

        del ctx
        try:
            record = await get_account(
                database_storage(storage), get_mcp_auth().user.id, account_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_account_response(record)

    @server.tool(name="update_money_account")
    async def update_money_account_tool(
        account_id: str,
        payload: AccountUpdateRequest,
        ctx: Context | None = None,
    ) -> AccountResponse:
        """Update one owner-scoped money account's safe metadata."""

        del ctx
        try:
            record = await update_account(
                database_storage(storage), get_mcp_auth().user.id, account_id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_account_response(record)

    @server.tool(name="archive_money_account")
    async def archive_money_account_tool(
        account_id: str, ctx: Context | None = None
    ) -> AccountResponse:
        """Archive one owner-scoped money account."""

        del ctx
        try:
            record = await archive_account(
                database_storage(storage), get_mcp_auth().user.id, account_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_account_response(record)

    @server.tool(name="restore_money_account")
    async def restore_money_account_tool(
        account_id: str, ctx: Context | None = None
    ) -> AccountResponse:
        """Restore one owner-scoped money account."""

        del ctx
        try:
            record = await restore_account(
                database_storage(storage), get_mcp_auth().user.id, account_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_account_response(record)

    @server.tool(name="create_money_payee")
    async def create_money_payee_tool(
        payload: PayeeCreateRequest, ctx: Context | None = None
    ) -> PayeeResponse:
        """Create an owner-scoped payee."""

        del ctx
        try:
            record = await create_payee(database_storage(storage), get_mcp_auth().user.id, payload)
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_payee_response(record)

    @server.tool(name="list_money_payees")
    async def list_money_payees_tool(
        include_archived: bool = False,
        search: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> PayeeListResponse:
        """List owner-scoped payees."""

        del ctx
        try:
            page = await list_payees(
                database_storage(storage),
                get_mcp_auth().user.id,
                PayeeListFilters(
                    include_archived=include_archived,
                    search=search,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return PayeeListResponse(
            items=[_money_payee_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_payee")
    async def get_money_payee_tool(payee_id: str, ctx: Context | None = None) -> PayeeResponse:
        """Return one owner-scoped payee."""

        del ctx
        try:
            record = await get_payee(database_storage(storage), get_mcp_auth().user.id, payee_id)
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_payee_response(record)

    @server.tool(name="update_money_payee")
    async def update_money_payee_tool(
        payee_id: str,
        payload: PayeeUpdateRequest,
        ctx: Context | None = None,
    ) -> PayeeResponse:
        """Update one owner-scoped payee."""

        del ctx
        try:
            record = await update_payee(
                database_storage(storage), get_mcp_auth().user.id, payee_id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_payee_response(record)

    @server.tool(name="archive_money_payee")
    async def archive_money_payee_tool(payee_id: str, ctx: Context | None = None) -> PayeeResponse:
        """Archive one owner-scoped payee."""

        del ctx
        try:
            record = await archive_payee(
                database_storage(storage), get_mcp_auth().user.id, payee_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_payee_response(record)

    @server.tool(name="restore_money_payee")
    async def restore_money_payee_tool(payee_id: str, ctx: Context | None = None) -> PayeeResponse:
        """Restore one owner-scoped payee."""

        del ctx
        try:
            record = await restore_payee(
                database_storage(storage), get_mcp_auth().user.id, payee_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_payee_response(record)

    @server.tool(name="create_money_category")
    async def create_money_category_tool(
        payload: CategoryCreateRequest, ctx: Context | None = None
    ) -> CategoryResponse:
        """Create an owner-scoped income or expense category."""

        del ctx
        try:
            record = await create_category(
                database_storage(storage), get_mcp_auth().user.id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_category_response(record)

    @server.tool(name="list_money_categories")
    async def list_money_categories_tool(
        include_archived: bool = False,
        kind: str | None = None,
        search: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> CategoryListResponse:
        """List owner-scoped money categories."""

        del ctx
        from .money.schemas import CategoryKind

        try:
            parsed_kind = CategoryKind(kind) if kind is not None else None
            page = await list_categories(
                database_storage(storage),
                get_mcp_auth().user.id,
                CategoryListFilters(
                    include_archived=include_archived,
                    kind=parsed_kind,
                    search=search,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except (MoneyError, ValueError) as exc:
            if isinstance(exc, MoneyError):
                _raise_money_tool(exc)
            raise ToolError("money_invalid_query: The money list query is invalid.") from exc
        return CategoryListResponse(
            items=[_money_category_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_category")
    async def get_money_category_tool(
        category_id: str, ctx: Context | None = None
    ) -> CategoryResponse:
        """Return one owner-scoped money category."""

        del ctx
        try:
            record = await get_category(
                database_storage(storage), get_mcp_auth().user.id, category_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_category_response(record)

    @server.tool(name="update_money_category")
    async def update_money_category_tool(
        category_id: str,
        payload: CategoryUpdateRequest,
        ctx: Context | None = None,
    ) -> CategoryResponse:
        """Update one owner-scoped money category."""

        del ctx
        try:
            record = await update_category(
                database_storage(storage), get_mcp_auth().user.id, category_id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_category_response(record)

    @server.tool(name="archive_money_category")
    async def archive_money_category_tool(
        category_id: str, ctx: Context | None = None
    ) -> CategoryResponse:
        """Archive one owner-scoped money category."""

        del ctx
        try:
            record = await archive_category(
                database_storage(storage), get_mcp_auth().user.id, category_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_category_response(record)

    @server.tool(name="restore_money_category")
    async def restore_money_category_tool(
        category_id: str, ctx: Context | None = None
    ) -> CategoryResponse:
        """Restore one owner-scoped money category."""

        del ctx
        try:
            record = await restore_category(
                database_storage(storage), get_mcp_auth().user.id, category_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_category_response(record)

    @server.tool(name="upsert_money_budget")
    async def upsert_money_budget_tool(
        period: str,
        category_id: str,
        currency_code: str,
        payload: BudgetUpsertRequest,
        ctx: Context | None = None,
    ) -> BudgetResponse:
        """Create or update one monthly category budget."""

        del ctx
        try:
            record = await upsert_budget(
                database_storage(storage),
                get_mcp_auth().user.id,
                period,
                category_id,
                currency_code,
                payload,
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_budget_response(record)

    @server.tool(name="list_money_budgets")
    async def list_money_budgets_tool(
        period: str | None = None,
        currency_code: str | None = None,
        category_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> BudgetListResponse:
        """List owner-scoped monthly category budgets."""

        del ctx
        try:
            page = await list_budgets(
                database_storage(storage),
                get_mcp_auth().user.id,
                BudgetListFilters(
                    period=period,
                    currency_code=currency_code,
                    category_id=category_id,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return BudgetListResponse(
            items=[_money_budget_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_budget")
    async def get_money_budget_tool(budget_id: str, ctx: Context | None = None) -> BudgetResponse:
        """Return one owner-scoped monthly category budget."""

        del ctx
        try:
            record = await get_budget(database_storage(storage), get_mcp_auth().user.id, budget_id)
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_budget_response(record)

    @server.tool(name="delete_money_budget")
    async def delete_money_budget_tool(budget_id: str, ctx: Context | None = None) -> str:
        """Delete one owner-scoped monthly category budget."""

        del ctx
        try:
            await delete_budget(database_storage(storage), get_mcp_auth().user.id, budget_id)
        except MoneyError as exc:
            _raise_money_tool(exc)
        return "Budget deleted."

    @server.tool(name="get_money_summary")
    async def get_money_summary_tool(
        period: str,
        currency_code: str = "PHP",
        ctx: Context | None = None,
    ) -> MoneySummaryResponse:
        """Return an owner-scoped money summary for one period and currency."""

        del ctx
        try:
            record = await get_money_summary(
                database_storage(storage),
                get_mcp_auth().user.id,
                period,
                currency_code,
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_summary_response(record)

    @server.tool(name="create_money_installment_plan")
    async def create_money_installment_plan_tool(
        payload: InstallmentPlanCreateRequest, ctx: Context | None = None
    ) -> InstallmentPlanResponse:
        """Create a credit-card purchase commitment charged over statement cycles."""

        del ctx
        try:
            record = await create_installment_plan(
                database_storage(storage), get_mcp_auth().user.id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_installment_plan_response(record)

    @server.tool(name="list_money_installment_plans")
    async def list_money_installment_plans_tool(
        account_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> InstallmentPlanListResponse:
        """List owner-scoped credit-card installment plans."""

        del ctx
        try:
            parsed_status = InstallmentPlanState(status) if status is not None else None
            page = await list_installment_plans(
                database_storage(storage),
                get_mcp_auth().user.id,
                InstallmentPlanListFilters(
                    account_id=account_id,
                    status=parsed_status,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except (MoneyError, ValueError) as exc:
            if isinstance(exc, MoneyError):
                _raise_money_tool(exc)
            raise ToolError("money_invalid_query: The money list query is invalid.") from exc
        return InstallmentPlanListResponse(
            items=[_money_installment_plan_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_installment_plan")
    async def get_money_installment_plan_tool(
        plan_id: str, ctx: Context | None = None
    ) -> InstallmentPlanResponse:
        """Return one owner-scoped installment plan and its statement charges."""

        del ctx
        try:
            record = await get_installment_plan(
                database_storage(storage), get_mcp_auth().user.id, plan_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_installment_plan_response(record)

    @server.tool(name="cancel_money_installment_plan")
    async def cancel_money_installment_plan_tool(
        plan_id: str, ctx: Context | None = None
    ) -> InstallmentPlanResponse:
        """Cancel future statement charges for one installment plan."""

        del ctx
        try:
            record = await cancel_installment_plan(
                database_storage(storage), get_mcp_auth().user.id, plan_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_installment_plan_response(record)

    @server.tool(name="process_due_money_installments")
    async def process_due_money_installments_tool(
        ctx: Context | None = None,
    ) -> InstallmentProcessResponse:
        """Catch up due statement charges for the authenticated owner."""

        del ctx
        try:
            processed_count = await process_due_installments(
                database_storage(storage), get_mcp_auth().user.id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return InstallmentProcessResponse(processed_count=processed_count)

    @server.tool(name="create_money_recurring_transaction")
    async def create_money_recurring_transaction_tool(
        payload: RecurringTransactionCreateRequest, ctx: Context | None = None
    ) -> RecurringTransactionResponse:
        """Create an owner-scoped recurring transaction schedule."""

        del ctx
        try:
            record = await create_recurring_transaction(
                database_storage(storage), get_mcp_auth().user.id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_recurring_transaction_response(record)

    @server.tool(name="list_money_recurring_transactions")
    async def list_money_recurring_transactions_tool(
        state: str | None = None,
        account_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> RecurringTransactionListResponse:
        """List owner-scoped recurring transaction schedules."""

        del ctx
        try:
            parsed_state = MoneyRecurrenceState(state) if state is not None else None
            page = await list_recurring_transactions(
                database_storage(storage),
                get_mcp_auth().user.id,
                RecurringTransactionListFilters(
                    state=parsed_state,
                    account_id=account_id,
                    search=search,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except (MoneyError, ValueError) as exc:
            if isinstance(exc, MoneyError):
                _raise_money_tool(exc)
            raise ToolError("money_invalid_query: The money list query is invalid.") from exc
        return RecurringTransactionListResponse(
            items=[_money_recurring_transaction_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_recurring_transaction")
    async def get_money_recurring_transaction_tool(
        recurring_transaction_id: str, ctx: Context | None = None
    ) -> RecurringTransactionResponse:
        """Return one owner-scoped recurring transaction schedule."""

        del ctx
        try:
            record = await get_recurring_transaction(
                database_storage(storage), get_mcp_auth().user.id, recurring_transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_recurring_transaction_response(record)

    @server.tool(name="update_money_recurring_transaction")
    async def update_money_recurring_transaction_tool(
        recurring_transaction_id: str,
        payload: RecurringTransactionUpdateRequest,
        ctx: Context | None = None,
    ) -> RecurringTransactionResponse:
        """Update future occurrences of one recurring transaction schedule."""

        del ctx
        try:
            record = await update_recurring_transaction(
                database_storage(storage),
                get_mcp_auth().user.id,
                recurring_transaction_id,
                payload,
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_recurring_transaction_response(record)

    @server.tool(name="pause_money_recurring_transaction")
    async def pause_money_recurring_transaction_tool(
        recurring_transaction_id: str, ctx: Context | None = None
    ) -> RecurringTransactionResponse:
        """Pause future occurrences of one recurring transaction schedule."""

        del ctx
        try:
            record = await pause_recurring_transaction(
                database_storage(storage), get_mcp_auth().user.id, recurring_transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_recurring_transaction_response(record)

    @server.tool(name="resume_money_recurring_transaction")
    async def resume_money_recurring_transaction_tool(
        recurring_transaction_id: str, ctx: Context | None = None
    ) -> RecurringTransactionResponse:
        """Resume one paused recurring transaction schedule."""

        del ctx
        try:
            record = await resume_recurring_transaction(
                database_storage(storage), get_mcp_auth().user.id, recurring_transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_recurring_transaction_response(record)

    @server.tool(name="end_money_recurring_transaction")
    async def end_money_recurring_transaction_tool(
        recurring_transaction_id: str, ctx: Context | None = None
    ) -> RecurringTransactionResponse:
        """End future occurrences of one recurring transaction schedule."""

        del ctx
        try:
            record = await end_recurring_transaction(
                database_storage(storage), get_mcp_auth().user.id, recurring_transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_recurring_transaction_response(record)

    @server.tool(name="process_due_money_recurring_transactions")
    async def process_due_money_recurring_transactions_tool(
        ctx: Context | None = None,
    ) -> RecurringProcessResponse:
        """Catch up due recurring transaction occurrences for the authenticated owner."""

        del ctx
        result = await process_due_recurring_transactions(
            database_storage(storage), get_mcp_auth().user.id
        )
        return RecurringProcessResponse(
            processed_count=result.processed_count,
            failed_count=result.failed_count,
        )

    @server.tool(name="create_money_transaction")
    async def create_money_transaction_tool(
        payload: TransactionCreateRequest, ctx: Context | None = None
    ) -> TransactionResponse:
        """Create one balanced owner-scoped money transaction."""

        del ctx
        try:
            record = await create_transaction(
                database_storage(storage), get_mcp_auth().user.id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="list_money_transactions")
    async def list_money_transactions_tool(
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        account_id: str | None = None,
        payee_id: str | None = None,
        category_id: str | None = None,
        currency_code: str | None = None,
        reconciliation_state: ReconciliationState | None = None,
        include_voided: bool = False,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> TransactionListResponse:
        """List owner-scoped money transactions with REST-equivalent filters."""

        del ctx
        try:
            page = await list_transactions(
                database_storage(storage),
                get_mcp_auth().user.id,
                TransactionListFilters(
                    date_from=date_from,
                    date_to=date_to,
                    search=search,
                    account_id=account_id,
                    payee_id=payee_id,
                    category_id=category_id,
                    currency_code=currency_code,
                    reconciliation_state=reconciliation_state,
                    include_voided=include_voided,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return TransactionListResponse(
            items=[_money_transaction_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_money_transaction")
    async def get_money_transaction_tool(
        transaction_id: str, ctx: Context | None = None
    ) -> TransactionResponse:
        """Return one owner-scoped money transaction."""

        del ctx
        try:
            record = await get_transaction(
                database_storage(storage), get_mcp_auth().user.id, transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="update_money_transaction")
    async def update_money_transaction_tool(
        transaction_id: str,
        payload: TransactionUpdateRequest,
        ctx: Context | None = None,
    ) -> TransactionResponse:
        """Update an unlocked owner-scoped money transaction."""

        del ctx
        try:
            record = await update_transaction(
                database_storage(storage), get_mcp_auth().user.id, transaction_id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="clear_money_posting")
    async def clear_money_posting_tool(
        transaction_id: str,
        posting_id: str,
        ctx: Context | None = None,
    ) -> TransactionResponse:
        """Mark one transaction posting cleared."""

        del ctx
        try:
            record = await clear_posting(
                database_storage(storage), get_mcp_auth().user.id, transaction_id, posting_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="reconcile_money_posting")
    async def reconcile_money_posting_tool(
        transaction_id: str,
        posting_id: str,
        ctx: Context | None = None,
    ) -> TransactionResponse:
        """Mark one cleared transaction posting reconciled."""

        del ctx
        try:
            record = await reconcile_posting(
                database_storage(storage), get_mcp_auth().user.id, transaction_id, posting_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="reverse_money_transaction")
    async def reverse_money_transaction_tool(
        transaction_id: str,
        payload: TransactionReverseRequest | None = None,
        ctx: Context | None = None,
    ) -> TransactionResponse:
        """Create a compensating transaction for a reconciled transaction."""

        del ctx
        try:
            record = await reverse_transaction(
                database_storage(storage), get_mcp_auth().user.id, transaction_id, payload
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="void_money_transaction")
    async def void_money_transaction_tool(
        transaction_id: str, ctx: Context | None = None
    ) -> TransactionResponse:
        """Void one standalone owner-scoped transaction before reconciliation."""

        del ctx
        try:
            record = await void_transaction(
                database_storage(storage), get_mcp_auth().user.id, transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="restore_money_transaction")
    async def restore_money_transaction_tool(
        transaction_id: str, ctx: Context | None = None
    ) -> TransactionResponse:
        """Restore one manually voided owner-scoped transaction."""

        del ctx
        try:
            record = await restore_transaction(
                database_storage(storage), get_mcp_auth().user.id, transaction_id
            )
        except MoneyError as exc:
            _raise_money_tool(exc)
        return _money_transaction_response(record)

    @server.tool(name="create_task")
    async def create_task_tool(payload: TaskCreateRequest, ctx: Context) -> TaskResponse:
        """Create an owner-scoped task."""

        del ctx
        try:
            record = await create_task(
                database_storage(storage),
                get_mcp_auth().user.id,
                payload,
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="list_tasks")
    async def list_tasks_tool(
        status: list[TaskStatus] | None = None,
        priority: list[TaskPriority] | None = None,
        tag: list[str] | None = None,
        search: str | None = None,
        due_from: datetime | None = None,
        due_to: datetime | None = None,
        scheduled_from: datetime | None = None,
        scheduled_to: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
        order: TaskListOrder = TaskListOrder.DUE,
        ctx: Context | None = None,
    ) -> TaskListResponse:
        """List owner-scoped tasks with the same filters as REST."""

        del ctx
        try:
            page = await list_tasks(
                database_storage(storage),
                get_mcp_auth().user.id,
                TaskListFilters(
                    statuses=tuple(status or ()),
                    priorities=tuple(priority or ()),
                    tags=tuple(tag or ()),
                    search=search,
                    due_from=due_from,
                    due_to=due_to,
                    scheduled_from=scheduled_from,
                    scheduled_to=scheduled_to,
                    limit=limit,
                    cursor=cursor,
                    order=order,
                ),
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return TaskListResponse(
            items=[_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_task_summary")
    async def get_task_summary_tool(
        timezone: str = "UTC",
        ctx: Context | None = None,
    ) -> TaskSummaryResponse:
        """Return global task-view counts and populated tags."""

        del ctx
        try:
            summary = await summarize_tasks(
                database_storage(storage),
                get_mcp_auth().user.id,
                timezone,
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return TaskSummaryResponse(
            all=summary.all,
            today=summary.today,
            upcoming=summary.upcoming,
            overdue=summary.overdue,
            high_priority=summary.high_priority,
            tags=[
                TaskTagSummaryResponse(
                    name=tag.name,
                    count=tag.count,
                    color=tag.color,
                    active=tag.active,
                )
                for tag in summary.tags
            ],
        )

    @server.tool(name="get_task")
    async def get_task_tool(task_id: str, ctx: Context) -> TaskResponse:
        """Return one owner-scoped task."""

        del ctx
        try:
            record = await get_task(database_storage(storage), get_mcp_auth().user.id, task_id)
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="reorder_task")
    async def reorder_task_tool(
        task_id: str,
        payload: TaskReorderRequest,
        ctx: Context,
    ) -> TaskResponse:
        """Move one owner-scoped task within the board ordering."""

        del ctx
        try:
            record = await reorder_task(
                database_storage(storage),
                get_mcp_auth().user.id,
                task_id,
                payload,
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="update_task")
    async def update_task_tool(
        task_id: str,
        payload: TaskUpdateRequest,
        ctx: Context,
    ) -> TaskResponse:
        """Apply a partial update to one owner-scoped task."""

        del ctx
        try:
            record = await update_task(
                database_storage(storage),
                get_mcp_auth().user.id,
                task_id,
                payload,
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="delete_task")
    async def delete_task_tool(task_id: str, ctx: Context) -> str:
        """Soft-delete one owner-scoped task."""

        del ctx
        try:
            await delete_task(database_storage(storage), get_mcp_auth().user.id, task_id)
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return "Task deleted."

    @server.tool(name="skip_task_occurrence")
    async def skip_task_occurrence_tool(task_id: str, ctx: Context) -> TaskResponse:
        """Skip and retain one recurring task occurrence."""

        del ctx
        try:
            record = await skip_task_occurrence(
                database_storage(storage), get_mcp_auth().user.id, task_id
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="list_task_series")
    async def list_task_series_tool(
        limit: int = 50,
        ctx: Context | None = None,
    ) -> TaskSeriesListResponse:
        """List owner-scoped recurrence series."""

        del ctx
        try:
            page = await list_task_series(database_storage(storage), get_mcp_auth().user.id, limit)
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return TaskSeriesListResponse(items=[_series_response(item) for item in page.items])

    @server.tool(name="get_task_series")
    async def get_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """Return one owner-scoped recurrence series."""

        del ctx
        try:
            record = await get_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="update_task_series")
    async def update_task_series_tool(
        series_id: str,
        payload: TaskSeriesUpdateRequest,
        ctx: Context,
    ) -> TaskSeriesResponse:
        """Update a recurrence template or rule."""

        del ctx
        try:
            record = await update_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id, payload
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="pause_task_series")
    async def pause_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """Pause future generation for a recurrence series."""

        del ctx
        try:
            record = await pause_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="resume_task_series")
    async def resume_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """Resume future generation for a recurrence series."""

        del ctx
        try:
            record = await resume_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="end_task_series")
    async def end_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """End future generation for a recurrence series."""

        del ctx
        try:
            record = await end_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError, AttachmentError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="create_note")
    async def create_note_tool(payload: NoteCreateRequest, ctx: Context) -> NoteResponse:
        """Create an owner-scoped HTML note; legacy Markdown input is normalized."""

        del ctx
        try:
            record = await create_note(
                database_storage(storage),
                get_mcp_auth().user.id,
                payload,
            )
        except (NoteError, TagError, AttachmentError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="list_notes")
    async def list_notes_tool(
        tag: list[str] | None = None,
        search: str | None = None,
        journal_date_from: date | None = None,
        journal_date_to: date | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> NoteListResponse:
        """List owner-scoped notes; response bodies are sanitized HTML."""

        del ctx
        try:
            page = await list_notes(
                database_storage(storage),
                get_mcp_auth().user.id,
                NoteListFilters(
                    tags=tuple(tag or ()),
                    search=search,
                    journal_date_from=journal_date_from,
                    journal_date_to=journal_date_to,
                    include_deleted=include_deleted,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except (NoteError, TagError, AttachmentError) as exc:
            _raise_note_tool(exc)
        return NoteListResponse(
            items=[_note_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_note")
    async def get_note_tool(note_id: str, ctx: Context) -> NoteResponse:
        """Return one active owner-scoped note with a sanitized HTML body."""

        del ctx
        try:
            record = await get_note(database_storage(storage), get_mcp_auth().user.id, note_id)
        except (NoteError, TagError, AttachmentError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="update_note")
    async def update_note_tool(
        note_id: str,
        payload: NoteUpdateRequest,
        ctx: Context,
    ) -> NoteResponse:
        """Update a note; legacy Markdown input is normalized and the body is returned as HTML."""

        del ctx
        try:
            record = await update_note(
                database_storage(storage), get_mcp_auth().user.id, note_id, payload
            )
        except (NoteError, TagError, AttachmentError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="delete_note")
    async def delete_note_tool(note_id: str, ctx: Context) -> str:
        """Soft-delete one active owner-scoped note."""

        del ctx
        try:
            await delete_note(database_storage(storage), get_mcp_auth().user.id, note_id)
        except (NoteError, TagError, AttachmentError) as exc:
            _raise_note_tool(exc)
        return "Note deleted."

    @server.tool(name="restore_note")
    async def restore_note_tool(note_id: str, ctx: Context) -> NoteResponse:
        """Restore one owner-scoped note."""

        del ctx
        try:
            record = await restore_note(database_storage(storage), get_mcp_auth().user.id, note_id)
        except (NoteError, TagError, AttachmentError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="append_activity_log")
    async def append_activity_log_tool(
        payload: ActivityLogCreateRequest,
        ctx: Context,
    ) -> ActivityLogResponse:
        """Append one owner-scoped activity record."""

        del ctx
        try:
            record = await append_log(
                database_storage(storage),
                get_mcp_auth().user.id,
                payload,
            )
        except ActivityLogError as exc:
            _raise_activity_log_tool(exc)
        return _activity_log_response(record)

    @server.tool(name="list_activity_logs")
    async def list_activity_logs_tool(
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> ActivityLogListResponse:
        """List owner-scoped activity records with bounded cursor pagination."""

        del ctx
        try:
            page = await list_logs(
                database_storage(storage),
                get_mcp_auth().user.id,
                ActivityLogFilters(
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except ActivityLogError as exc:
            _raise_activity_log_tool(exc)
        return ActivityLogListResponse(
            items=[_activity_log_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    return server
