# %%
import pandas as pd

# 1. Read the Excel file
# sheet_name: Name of the worksheet.
# skiprows=5: Skips the first 5 rows (Excel starts at 1, so we skip through row 5).
# nrows=2: Reads only 2 rows (row 6 contains the categories and row 7 the subcategories).
# header=None: Specifies that the first row should not be used as column names.
df = pd.read_excel(
    'MISSION_CONTEXT_MM.xlsx',
    sheet_name='CONTEXT MM NEW',
    skiprows=5,
    nrows=2,
    header=None
)

# %% name

# 2. Extract and process the Categories row (row 0 of the DataFrame)
# We use ffill() so that merged cells are propagated to the right.
categories = df.iloc[0].ffill()

# 3. Extract the Subcategories row (row 1 of the DataFrame)
subcategories = df.iloc[1]

# 4. Create the dictionary
result_dictionary = {}

# Iterate over both rows at the same time
for category, subcategory in zip(categories, subcategories):

    # Ignore null values and the initial label columns
    # ("CATEGORY" and "SUB-CATEGORY").
    if (
        pd.isna(category)
        or pd.isna(subcategory)
        or category == 'CATEGORY'
        or subcategory == 'SUB-CATEGORY'
    ):
        continue

    # Remove possible leading and trailing spaces from the text.
    category = str(category).strip()
    subcategory = str(subcategory).strip()

    # If the category is not yet in the dictionary, initialize it
    # with an empty list.
    if category not in result_dictionary:
        result_dictionary[category] = []

    # Add the subcategory to the corresponding list.
    result_dictionary[category].append(subcategory)

# Display the final result.
print(result_dictionary)
# %%
