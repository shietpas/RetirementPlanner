(CsvPath as text) as table =>
let
    Source = Csv.Document(
        File.Contents(CsvPath),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Headers,
        {
            {"scenario", type text},
            {"row_type", type text},
            {"metric_scope", type text},
            {"metric_category", type text},
            {"metric_name", type text},
            {"year", Int64.Type},
            {"calendar_year", Int64.Type},
            {"user_age", Int64.Type},
            {"spouse_age", Int64.Type},
            {"owner", type text},
            {"flow_name", type text},
            {"account_name", type text},
            {"account_type", type text},
            {"tax_treatment", type text},
            {"value", type number}
        }
    )
in
    Typed