from collections.abc import Iterable


def create_index(
    tbl: str,
    cols: Iterable,
    *,
    name: str = '',
    unique: bool = False,
) -> str:
    cols = tuple(str(col) for col in cols)
    unq = 'UNIQUE' if unique else ''
    name = name if name else "_".join(cols)
    res = f'CREATE {unq} INDEX IF NOT EXISTS idx_{tbl}_{name} ON {tbl}({",".join(cols)});'
    return res


def on_conflict(
    key_cols: Iterable[str],
    confilcting_cols: Iterable[str],
):
    confilcting_cols = ',\n\t\t'.join(
        f'{col}=excluded.{col}' for col in confilcting_cols
    )
    if confilcting_cols:
        return (
    f'''ON CONFLICT({', '.join(key_cols)}) DO UPDATE SET
		{confilcting_cols}'''
        )
    return 'ON CONFLICT DO NOTHING'
