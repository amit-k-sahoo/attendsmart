"""
Real participant roster, deduplicated from:
'List of attendees - IIT K - CDAIO 02 Campus Immersion.xlsx'

Per the Smart Classroom AI Challenge data guidelines: real names are used to
personalize the prototype; every attribute attached to a name below
(attendance, engagement, quiz scores, risk labels, etc.) is 100% synthetic
demo data generated for this capstone project and does not reflect any
real academic or attendance record.
"""

ROSTER = [
    "Thirunavukarasu Jayavelu",
    "Manikya Rao Segu",
    "Jayaprakash Mahankali",
    "Ajay Kumar S V",
    "Manoj Kumar",
    "Kumar Kanishka",
    "Suyash Jain",
    "Abhijit Wagh",
    "Prakash Bhawnani",
    "Deepak Khandelwal",
    "Nikhilesh Kumar",
    "Duraimurugan Kandasamy",
    "Gagan Chawla",
    "Amit Kumar Sahoo",
    "Manish Madan Sharma",
    "Rajesh Manoharan",
    "Hari Nair",
    "Adesh Kumar Tripathi",
    "Sivajothi Gunasekaran",
    "Ayush Taliwal",
    "Ravi Kumar",
    "Arvind Suryanarayanan",
    "Milan Gupta",
    "Swaroop Madakasira",
    "Karthick E",
    "Randhir Singh",
    "Ayush Saxena",
    "Manish",
    "Sandeep Chauhan",
    "Kannan Arumugam",
    "Ankush Arora",
    "J Pravin Kumar",
    "Hiteshchandra Patel",
    "Raghuraj Deshpande",
    "Krishna Kumar Subramanian",
    "Snehal R Singh",
    "Mirle Seetharamu Manjunath",
    "Jayanthi Mani",
    "Prakshi Bansal",
]

assert len(ROSTER) == len(set(ROSTER)), "Duplicate names found in roster!"
