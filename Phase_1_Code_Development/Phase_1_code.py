# %%
import pandas as pd
import numpy as np

class mission:
    """ This class creates the different attributes and functions needed to complete the steps of Phase 1 'Operational Scenario Development' of the methodology"""
    def __init__(self, mission_code):
        # This dictionary relates the code (key) to the name (value) of the selected mission
        mission_name = {'IA':'Initial Attack', 'EA':'Extended Attack', 'LFO':'Large Fire Operations', 'WSP':'WUI/Structure Protection','FRM':'Fire Reconnaissance/Monitoring'}

        # This list provides a brief definition of each mission class
        intent_definition = ['Rapid initial wildfire response using first-arriving resources', 'Response after the fire exceeds initial attack capability', 'Sustained management and suppression of large or complex fires', 'Protect structures and exposed assets threatened by wildfire', 'Detect, observe, and report fire status and evolution']

        # This list of lists provides the operational functions associated with the selected mission
        mission_to_function = [['Detection', 'Monitoring', 'Suppression', 'Confinement'], ['Detection', 'Monitoring', 'Suppression', 'Point Protection','Confinement'], ['Detection', 'Monitoring', 'Suppression', 'Point Protection','Confinement'], ['Detection', 'Monitoring', 'Suppression', 'Point Protection'], ['Detection', 'Monitoring']]

        # This list provides the names of the baseline capabilities
        BL_capability = ['Observation & detection ability', 'Spatial coverage & initial-response reach', 'Localization, alerting, & interpretation ability', 'Timeliness & update continuity', 'Suppression-effect delivery ability', 'Access, deployment, & mobility ability', 'Coordination & synchronization ability', 'Operational sustainment ability','Confinement-support ability', 'Point-protection effect ability', 'Local exposure assessment & prioritization ability']

        # This dictionary provides the link between the baseline capability code (key) and its corresponding name (value)
        self.code_to_capability = {'CB1': 'Observation & detection ability', 'CB2': 'Spatial coverage & initial-response reach', 'CB3': 'Localization, alerting, & interpretation ability', 'CB4': 'Timeliness & update continuity', 'CB5': 'Suppression-effect delivery ability', 'CB6': 'Access, deployment, & mobility ability', 'CB7': 'Coordination & synchronization ability', 'CB8': 'Operational sustainment ability', 'CB9': 'Confinement-support ability', 'CB10': 'Point-protection effect ability', 'CB11': 'Local exposure assessment & prioritization ability'}            

        # This dictionary provides the link between each baseline capability code (key) and its corresponding list of linked capability dimensions (value)
        dimension_to_BL_capability = {'CB1':['Detection & discrimination performance','Observation coverage & persistence','Fire-state information quality'], 'CB2': ['Spatial search coverage',
        'Initial-response reach & timeliness'], 'CB3': ['Geolocation accuracy','Alert-dissemination connectivity & continuity','Fire-state interpretation & forecast support'], 'CB4': ['Detection-to-alert timeliness','Update timeliness & frequency','Tracking continuity'], 'CB5': ['Suppression-effect generation & placement performance', 'Delivery-cycle continuity'], 'CB6': ['Initial-response reach & timeliness','On-incident access & mobility','Timely access & deployment to exposed assets'], 'CB7': ['Alert-dissemination connectivity & continuity', 'Multi-resource coordination','Confinement coordination & sustainment'], 'CB8':
        ['Delivery-cycle continuity','Operational sustainment','Local protection persistence & sustainment','Confinement coordination & sustainment'], 'CB9': ['Control-line/barrier establishment performance','Barrier identification & exploitation','Line holding, security, & breach response'], 'CB10': ['Asset-protection effect capacity & effectiveness','Local protection persistence & sustainment'], 'CB11': ['Local exposure & defensibility assessment','Asset-prioritization & triage support']}
        
        # This list comprehension generates the link between the mission intent and the mission name
        mission_intent ={code:intent for code, intent in zip(mission_name, intent_definition)}

        # This list comprehension generates the operational functions from the selected mission
        operational_functions ={code:ops for code, ops in zip(mission_name, mission_to_function)}

        # This dictionary relates each function (key) with its associated capability dimensions
        functs_to_capab_dims ={'Detection':['Detection & discrimination performance','Spatial search coverage', 'Geolocation accuracy', 'Detection-to-alert timeliness', 'Alert-dissemination connectivity & continuity'],    'Monitoring': ['Observation coverage & persistence', 'Update timeliness & frequency','Tracking continuity', 'Fire-state information quality', 'Fire-state interpretation & forecast support'], 'Suppression':['Suppression-effect generation & placement performance','Initial-response reach & timeliness','On-incident access & mobility', 'Delivery-cycle continuity', 'Multi-resource coordination', 'Operational sustainment'], 'Point Protection': ['Asset-protection effect capacity & effectiveness', 'Timely access & deployment to exposed assets', 'Local exposure & defensibility assessment','Asset-prioritization & triage support',
        'Local protection persistence & sustainment'],
        'Confinement': ['Control-line/barrier establishment performance', 'Barrier identification & exploitation', 'Line holding, security, & breach response', 'On-incident access & mobility','Confinement coordination & sustainment']}
        
        # These command create the attributes of the class
        self.mc = mission_code
        self.name = mission_name[mission_code]
        self.intent = mission_intent[mission_code]
        self.functions = operational_functions[mission_code]
        # This dictionary creates the list of capability dimensions as a list of lists
        capability_dims = [functs_to_capab_dims[func] for func in self.functions]
        # This command generates the capability dimensions as one continuous list
        self.capability_dims = list(set([item for sublist in capability_dims for item in sublist]))

        # Dictionary comprehension to generate the existing baseline capabilities
        cap_set = set(self.capability_dims) 
        self.BL_capability = {key: [v for v in values if v not in cap_set] for key, values in dimension_to_BL_capability.items() if any(v in cap_set for v in values)} # Condition at least one item

    def summary(self):
        '''This function prints the mission name, mission definition, the operational functions, the linked capability dimensions, and the BL capabilities.  For the latter, it also prints the missing capability dimensions when the capability is degraded '''
        print('Mission class:', self.name)
        print()
        print('Mission definition:', self.intent)
        print()
        print('Operational functions decomposition:', np.array(self.functions), sep="\n")
        print()
        print('Linked capability dimensions:', np.array(self.capability_dims), sep="\n")
        print()
        print('Baseline capabilities:',)
        # This 'for' loop verifies if the values of the BL_capability dictionary contain a missing capability dimension and prints it out below the degraded BL capability
        for code, values in self.BL_capability.items():
            print('-', self.code_to_capability[code], end='') 
            if values: # This condition verifies if the list contains elements
                print(' | Partial capability')
                print('Missing dimensions:', values)
            else:
                print(' | Full capability')    
        
test_1 = mission('LFO')
test_1.summary()    



# %%

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
