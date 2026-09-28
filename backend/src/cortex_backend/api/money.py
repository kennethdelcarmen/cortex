"""HTTP adapters for the money domain."""

from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..auth.service import CurrentAuth
from ..money.errors import MoneyError
from ..money.schemas import (
    AccountCreateRequest,
    AccountListResponse,
    AccountResponse,
    AccountUpdateRequest,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpsertRequest,
    CategoryCreateRequest,
    CategoryKind,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdateRequest,
    MoneySummaryResponse,
    PayeeCreateRequest,
    PayeeListResponse,
    PayeeResponse,
    PayeeUpdateRequest,
    PostingResponse,
    ReconciliationState,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
    TransactionReverseRequest,
    TransactionState,
    TransactionUpdateRequest,
)
from ..money.service import (
    AccountListFilters,
    AccountRecord,
    BudgetListFilters,
    BudgetRecord,
    CategoryListFilters,
    CategoryRecord,
    MoneySummaryRecord,
    PayeeListFilters,
    PayeeRecord,
    TransactionListFilters,
    TransactionRecord,
    archive_account,
    archive_category,
    archive_payee,
    clear_posting,
    create_account,
    create_category,
    create_payee,
    create_transaction,
    delete_budget,
    get_account,
    get_budget,
    get_category,
    get_money_summary,
    get_payee,
    get_transaction,
    list_accounts,
    list_budgets,
    list_categories,
    list_payees,
    list_transactions,
    reconcile_posting,
    restore_account,
    restore_category,
    restore_payee,
    reverse_transaction,
    update_account,
    update_category,
    update_payee,
    update_transaction,
    upsert_budget,
)
from ..storage import DatabaseStorage
from .dependencies import get_current_auth, get_database_storage, require_csrf_auth

router = APIRouter(prefix="/api/v1/money", tags=["money"])


def _raise_http(error: MoneyError) -> NoReturn:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


def _account_response(record: AccountRecord) -> AccountResponse:
    return AccountResponse(
        id=record.id,
        name=record.name,
        account_type=record.account_type,
        institution_name=record.institution_name,
        last_four=record.last_four,
        currency_code=record.currency_code,
        opening_balance=record.opening_balance,
        balance=record.balance,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _payee_response(record: PayeeRecord) -> PayeeResponse:
    return PayeeResponse(
        id=record.id,
        name=record.name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _category_response(record: CategoryRecord) -> CategoryResponse:
    return CategoryResponse(
        id=record.id,
        name=record.name,
        kind=record.kind,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _budget_response(record: BudgetRecord) -> BudgetResponse:
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


def _transaction_response(record: TransactionRecord) -> TransactionResponse:
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
    )


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account_route(
    payload: AccountCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> AccountResponse:
    try:
        return _account_response(await create_account(storage, auth.user.id, payload))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/accounts", response_model=AccountListResponse)
async def list_accounts_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    include_archived: bool = False,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> AccountListResponse:
    try:
        page = await list_accounts(
            storage,
            auth.user.id,
            AccountListFilters(
                include_archived=include_archived,
                search=search,
                limit=limit,
                cursor=cursor,
            ),
        )
    except MoneyError as exc:
        _raise_http(exc)
    return AccountListResponse(
        items=[_account_response(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.post("/accounts/{account_id}/archive", response_model=AccountResponse)
async def archive_account_route(
    account_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> AccountResponse:
    try:
        return _account_response(await archive_account(storage, auth.user.id, account_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.post("/accounts/{account_id}/restore", response_model=AccountResponse)
async def restore_account_route(
    account_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> AccountResponse:
    try:
        return _account_response(await restore_account(storage, auth.user.id, account_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account_route(
    account_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> AccountResponse:
    try:
        return _account_response(await get_account(storage, auth.user.id, account_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account_route(
    account_id: str,
    payload: AccountUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> AccountResponse:
    try:
        return _account_response(await update_account(storage, auth.user.id, account_id, payload))
    except MoneyError as exc:
        _raise_http(exc)


@router.post("/payees", response_model=PayeeResponse, status_code=status.HTTP_201_CREATED)
async def create_payee_route(
    payload: PayeeCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> PayeeResponse:
    try:
        return _payee_response(await create_payee(storage, auth.user.id, payload))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/payees", response_model=PayeeListResponse)
async def list_payees_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    include_archived: bool = False,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> PayeeListResponse:
    try:
        page = await list_payees(
            storage,
            auth.user.id,
            PayeeListFilters(
                include_archived=include_archived,
                search=search,
                limit=limit,
                cursor=cursor,
            ),
        )
    except MoneyError as exc:
        _raise_http(exc)
    return PayeeListResponse(
        items=[_payee_response(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.post("/payees/{payee_id}/archive", response_model=PayeeResponse)
async def archive_payee_route(
    payee_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> PayeeResponse:
    try:
        return _payee_response(await archive_payee(storage, auth.user.id, payee_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.post("/payees/{payee_id}/restore", response_model=PayeeResponse)
async def restore_payee_route(
    payee_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> PayeeResponse:
    try:
        return _payee_response(await restore_payee(storage, auth.user.id, payee_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/payees/{payee_id}", response_model=PayeeResponse)
async def get_payee_route(
    payee_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> PayeeResponse:
    try:
        return _payee_response(await get_payee(storage, auth.user.id, payee_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.patch("/payees/{payee_id}", response_model=PayeeResponse)
async def update_payee_route(
    payee_id: str,
    payload: PayeeUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> PayeeResponse:
    try:
        return _payee_response(await update_payee(storage, auth.user.id, payee_id, payload))
    except MoneyError as exc:
        _raise_http(exc)


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category_route(
    payload: CategoryCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> CategoryResponse:
    try:
        return _category_response(await create_category(storage, auth.user.id, payload))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    include_archived: bool = False,
    kind: CategoryKind | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> CategoryListResponse:
    try:
        page = await list_categories(
            storage,
            auth.user.id,
            CategoryListFilters(
                include_archived=include_archived,
                kind=kind,
                search=search,
                limit=limit,
                cursor=cursor,
            ),
        )
    except MoneyError as exc:
        _raise_http(exc)
    return CategoryListResponse(
        items=[_category_response(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.post("/categories/{category_id}/archive", response_model=CategoryResponse)
async def archive_category_route(
    category_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> CategoryResponse:
    try:
        return _category_response(await archive_category(storage, auth.user.id, category_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.post("/categories/{category_id}/restore", response_model=CategoryResponse)
async def restore_category_route(
    category_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> CategoryResponse:
    try:
        return _category_response(await restore_category(storage, auth.user.id, category_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category_route(
    category_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> CategoryResponse:
    try:
        return _category_response(await get_category(storage, auth.user.id, category_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category_route(
    category_id: str,
    payload: CategoryUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> CategoryResponse:
    try:
        return _category_response(
            await update_category(storage, auth.user.id, category_id, payload)
        )
    except MoneyError as exc:
        _raise_http(exc)


@router.put(
    "/budgets/{period}/{category_id}/{currency_code}",
    response_model=BudgetResponse,
)
async def upsert_budget_route(
    period: str,
    category_id: str,
    currency_code: str,
    payload: BudgetUpsertRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> BudgetResponse:
    try:
        return _budget_response(
            await upsert_budget(
                storage,
                auth.user.id,
                period,
                category_id,
                currency_code,
                payload,
            )
        )
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/budgets", response_model=BudgetListResponse)
async def list_budgets_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    period: str | None = None,
    currency_code: str | None = None,
    category_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> BudgetListResponse:
    try:
        page = await list_budgets(
            storage,
            auth.user.id,
            BudgetListFilters(
                period=period,
                currency_code=currency_code,
                category_id=category_id,
                limit=limit,
                cursor=cursor,
            ),
        )
    except MoneyError as exc:
        _raise_http(exc)
    return BudgetListResponse(
        items=[_budget_response(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.get("/summary", response_model=MoneySummaryResponse)
async def money_summary_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    period: str,
    currency_code: str = "PHP",
) -> MoneySummaryResponse:
    try:
        return _money_summary_response(
            await get_money_summary(storage, auth.user.id, period, currency_code)
        )
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/budgets/{budget_id}", response_model=BudgetResponse)
async def get_budget_route(
    budget_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> BudgetResponse:
    try:
        return _budget_response(await get_budget(storage, auth.user.id, budget_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_route(
    budget_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> Response:
    try:
        await delete_budget(storage, auth.user.id, budget_id)
    except MoneyError as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction_route(
    payload: TransactionCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TransactionResponse:
    try:
        return _transaction_response(await create_transaction(storage, auth.user.id, payload))
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    date_from: date | None = None,
    date_to: date | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    account_id: str | None = None,
    payee_id: str | None = None,
    category_id: str | None = None,
    currency_code: str | None = None,
    reconciliation_state: ReconciliationState | None = None,
    include_voided: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> TransactionListResponse:
    try:
        page = await list_transactions(
            storage,
            auth.user.id,
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
        _raise_http(exc)
    return TransactionListResponse(
        items=[_transaction_response(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.post(
    "/transactions/{transaction_id}/postings/{posting_id}/clear",
    response_model=TransactionResponse,
)
async def clear_posting_route(
    transaction_id: str,
    posting_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TransactionResponse:
    try:
        return _transaction_response(
            await clear_posting(storage, auth.user.id, transaction_id, posting_id)
        )
    except MoneyError as exc:
        _raise_http(exc)


@router.post(
    "/transactions/{transaction_id}/postings/{posting_id}/reconcile",
    response_model=TransactionResponse,
)
async def reconcile_posting_route(
    transaction_id: str,
    posting_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TransactionResponse:
    try:
        return _transaction_response(
            await reconcile_posting(storage, auth.user.id, transaction_id, posting_id)
        )
    except MoneyError as exc:
        _raise_http(exc)


@router.post("/transactions/{transaction_id}/reverse", response_model=TransactionResponse)
async def reverse_transaction_route(
    transaction_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
    payload: TransactionReverseRequest | None = None,
) -> TransactionResponse:
    try:
        return _transaction_response(
            await reverse_transaction(storage, auth.user.id, transaction_id, payload)
        )
    except MoneyError as exc:
        _raise_http(exc)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_route(
    transaction_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> TransactionResponse:
    try:
        return _transaction_response(await get_transaction(storage, auth.user.id, transaction_id))
    except MoneyError as exc:
        _raise_http(exc)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction_route(
    transaction_id: str,
    payload: TransactionUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TransactionResponse:
    try:
        return _transaction_response(
            await update_transaction(storage, auth.user.id, transaction_id, payload)
        )
    except MoneyError as exc:
        _raise_http(exc)
