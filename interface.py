import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector
import hashlib  # For hashing passwords
import sys

# --- !!! IMPORTANT: CONFIGURE YOUR MYSQL CONNECTION HERE !!! ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',         # Your MySQL username
    'password': 'patlu', # Your MySQL password
    'database': 'restaurant_db' # The database to create/use
}


# --- STYLING ---
STYLE_CONFIG = {
    "BG_COLOR": "#f0f2f5",      # Light grey background
    "FRAME_COLOR": "#ffffff",   # White for main frames
    "PRIMARY_COLOR": "#0052cc", # A nice blue
    "SECONDARY_COLOR": "#ffc400", # A golden yellow accent
    "TEXT_COLOR": "#172b4d",
    "HEADER_FONT": ("Arial", 18, "bold"),
    "BODY_FONT": ("Arial", 12),
    "BUTTON_FONT": ("Arial", 12, "bold")
}

# --- DATABASE MANAGER ---
class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.connect()

    def connect(self):
        try:
            # Try to connect to the specified database
            self.connection = mysql.connector.connect(**self.config)
            print("Successfully connected to database.")
        except mysql.connector.Error as err:
            if err.errno == 1049: # Unknown database
                print("Database not found. Attempting to create and set up...")
                self.initial_setup()
                # Try connecting again after setup
                try:
                    self.connection = mysql.connector.connect(**self.config)
                    print("Database created and connected successfully.")
                except mysql.connector.Error as err:
                    print(f"Failed to connect after setup: {err}")
                    messagebox.showerror("Database Error", f"Failed to connect after setup: {err}")
                    sys.exit(1)
            else:
                # Other error (e.g., wrong password, server down)
                print(f"Error: {err}")
                messagebox.showerror(
                    "Database Error", 
                    f"Could not connect to MySQL: {err}\n"
                    "Please check your credentials in DB_CONFIG."
                )
                sys.exit(1)

    def initial_setup(self):
        """Connects to MySQL server and runs the setup script."""
        temp_config = self.config.copy()
        db_name = temp_config.pop('database') # Get 'restaurant_db' and remove it for now
        
        try:
            # Connect to MySQL server (without a specific db)
            temp_conn = mysql.connector.connect(**temp_config)
            cursor = temp_conn.cursor()
            
            # Split script into individual commands
            sql_commands = [cmd.strip() for cmd in SETUP_SQL_SCRIPT.split(';\n') if cmd.strip()]
            
            for command in sql_commands:
                try:
                    if command:
                        cursor.execute(command)
                except mysql.connector.Error as err:
                    # Ignore "database exists" or "table exists" errors
                    if err.errno == 1007 or err.errno == 1050:
                        print(f"Ignoring error: {err}")
                    else:
                        print(f"Error executing command: {command}\n{err}")
            
            temp_conn.commit()
            cursor.close()
            temp_conn.close()
            print("Database setup script executed.")
        except mysql.connector.Error as err:
            print(f"Failed during initial setup: {err}")
            messagebox.showerror("Setup Error", f"Failed to set up database: {err}")
            sys.exit(1)

    def get_cursor(self):
        # Check if connection is lost and reconnect if needed
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
            cursor = self.connection.cursor(dictionary=True)
            # Try a simple query to ensure connection is really alive
            cursor.execute("SELECT 1")
            cursor.fetchall()
            # If we are here, connection is good. Re-create cursor.
            return self.connection.cursor(dictionary=True)
        except mysql.connector.Error as err:
            print(f"Reconnecting due to error: {err}")
            self.connect() # Attempt to reconnect
            return self.connection.cursor(dictionary=True)


    def execute_query(self, query, params=()):
        cursor = self.get_cursor()
        try:
            cursor.execute(query, params)
            self.connection.commit()
            cursor.close()
            return True
        except mysql.connector.Error as err:
            print(f"Query Error: {err}")
            self.connection.rollback()
            cursor.close()
            return False

    def fetch_query(self, query, params=()):
        cursor = self.get_cursor()
        try:
            cursor.execute(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except mysql.connector.Error as err:
            print(f"Fetch Error: {err}")
            cursor.close()
            return []
    
    # --- Password Hashing ---
    def hash_password(self, password):
        """Hashes a password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    def check_password(self, plain_password, hashed_password):
        """Checks if the plain password matches the hashed one."""
        return self.hash_password(plain_password) == hashed_password
    
    # --- User Functions ---
    def create_user(self, username, password):
        hashed_pw = self.hash_password(password)
        query = "INSERT INTO users (username, password_hash) VALUES (%s, %s)"
        cursor = self.get_cursor()
        try:
            cursor.execute(query, (username, hashed_pw))
            self.connection.commit()
            cursor.close()
            return "SUCCESS" # Return a success code
        except mysql.connector.Error as err:
            print(f"Create User Error: {err}")
            self.connection.rollback()
            cursor.close()
            if err.errno == 1062: # Duplicate entry
                return "DUPLICATE"
            return f"OTHER_ERROR: {err}" # Any other error

    def validate_user(self, username, password):
        query = "SELECT user_id, password_hash FROM users WHERE username = %s"
        users = self.fetch_query(query, (username,))
        if users:
            user = users[0]
            if self.check_password(password, user['password_hash']):
                return user['user_id'] # Login success
        return None # Login fail

    # --- Menu Functions ---
    def get_menu_items(self):
        query = "SELECT item_id, name, description, price, category FROM menu_items"
        return self.fetch_query(query)
    
    # --- Order Functions ---
    def create_order(self, user_id, total_amount, items):
        order_query = "INSERT INTO orders (user_id, total_amount) VALUES (%s, %s)"
        try:
            cursor = self.get_cursor()
            cursor.execute(order_query, (user_id, total_amount))
            order_id = cursor.lastrowid
            
            # Now, add all items to the order_items table
            item_query = """
                INSERT INTO order_items (order_id, item_id, quantity, price_per_item) 
                VALUES (%s, %s, %s, %s)
            """
            item_data = [
                (order_id, item['item_id'], item['quantity'], item['price'])
                for item in items
            ]
            cursor.executemany(item_query, item_data)
            
            self.connection.commit()
            cursor.close()
            return True
        except mysql.connector.Error as err:
            print(f"Order Error: {err}")
            self.connection.rollback()
            cursor.close()
            return False
            
    # --- Feedback Functions ---
    def submit_feedback(self, user_id, rating, comments):
        query = "INSERT INTO feedback (user_id, rating, comments) VALUES (%s, %s, %s)"
        return self.execute_query(query, (user_id, rating, comments))

# +++ HELPER CLASS FOR SCROLLABLE FRAME +++
# We need this to make a scrollable list of checkboxes
class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        # Create a canvas
        self.canvas = tk.Canvas(self, bg=STYLE_CONFIG["FRAME_COLOR"], highlightthickness=0)
        
        # Create a scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # This frame will hold all the widgets (checkboxes, labels, etc.)
        self.scrollable_frame = ttk.Frame(self.canvas, style='Content.TFrame')

        # Bind the scrollable frame's configure event to the canvas
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        # Create the canvas window
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # Configure the canvas to use the scrollbar
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Pack the canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- THIS IS THE FIX ---
        # Bind mouse wheel scrolling to the canvas, not the whole app
        # This handles Windows, macOS, and Linux scrolling
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _bind_mousewheel(self, event):
        """Binds scroll events when mouse enters the canvas."""
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)  # Windows/macOS
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)     # Linux (scroll up)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)     # Linux (scroll down)

    def _unbind_mousewheel(self, event):
        """Unbinds scroll events when mouse leaves the canvas."""
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        """Handles cross-platform mouse wheel scrolling."""
        if hasattr(event, 'delta'): # Windows/macOS
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4: # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5: # Linux scroll down
            self.canvas.yview_scroll(1, "units")


# --- MAIN APPLICATION CONTROLLER ---
class RestaurantApp(tk.Tk):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.current_user_id = None
        self.current_user_name = None
        self.current_order = {} # A dictionary to store the cart

        self.title("Restaurant Management System")
        self.geometry("900x700")
        self.configure(bg=STYLE_CONFIG["BG_COLOR"])

        # Configure global ttk styles
        self.configure_styles()

        # Main container to hold pages
        self.container = ttk.Frame(self, padding=10)
        self.container.pack(fill="both", expand=True)

        # Show the login page first
        self.show_frame(LoginPage)

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam') # Use a modern theme

        # Frame styles
        style.configure('TFrame', background=STYLE_CONFIG["BG_COLOR"])
        style.configure('Content.TFrame', background=STYLE_CONFIG["FRAME_COLOR"])
        
        # Label styles
        style.configure('TLabel', 
                        font=STYLE_CONFIG["BODY_FONT"], 
                        background=STYLE_CONFIG["BG_COLOR"],
                        foreground=STYLE_CONFIG["TEXT_COLOR"])
        style.configure('Header.TLabel', 
                        font=STYLE_CONFIG["HEADER_FONT"], 
                        background=STYLE_CONFIG["BG_COLOR"],
                        foreground=STYLE_CONFIG["PRIMARY_COLOR"],
                        padding=10)
        style.configure('Content.TLabel', 
                        background=STYLE_CONFIG["FRAME_COLOR"])
        style.configure('Error.TLabel', 
                        background=STYLE_CONFIG["BG_COLOR"],
                        foreground='red',
                        font=("Arial", 10))
        
        # Button styles
        style.configure('TButton', 
                        font=STYLE_CONFIG["BUTTON_FONT"], 
                        padding=(10, 5))
        style.configure('Primary.TButton', 
                        background=STYLE_CONFIG["PRIMARY_COLOR"], 
                        foreground='white')
        style.map('Primary.TButton',
                  background=[('active', STYLE_CONFIG["PRIMARY_COLOR"])])
        
        style.configure('Secondary.TButton', 
                        background=STYLE_CONFIG["SECONDARY_COLOR"], 
                        foreground=STYLE_CONFIG["TEXT_COLOR"])
        style.map('Secondary.TButton',
                  background=[('active', STYLE_CONFIG["SECONDARY_COLOR"])])

        # Entry and Treeview
        style.configure('TEntry', 
                        font=STYLE_CONFIG["BODY_FONT"], 
                        padding=5)
        style.configure('Treeview', 
                        font=STYLE_CONFIG["BODY_FONT"], 
                        rowheight=25)
        style.configure('Treeview.Heading', 
                        font=STYLE_CONFIG["BUTTON_FONT"])
        
        # --- ADD THESE NEW STYLES ---
        # Checkbutton
        style.configure('TCheckbutton', 
                        background=STYLE_CONFIG["FRAME_COLOR"], 
                        font=STYLE_CONFIG["BODY_FONT"],
                        foreground=STYLE_CONFIG["TEXT_COLOR"])
        style.map('TCheckbutton',
                  background=[('active', STYLE_CONFIG["FRAME_COLOR"])],
                  indicatorbackground=[('active', STYLE_CONFIG["FRAME_COLOR"])])
        
        # Spinbox
        style.configure('TSpinbox', 
                        font=STYLE_CONFIG["BODY_FONT"], 
                        padding=5)
        
        # Scale (for Feedback)
        style.configure('TScale', 
                        background=STYLE_CONFIG["FRAME_COLOR"])
        # --- END OF NEW STYLES ---

        # Notebook (Tabs)
        style.configure('TNotebook', 
                        background=STYLE_CONFIG["BG_COLOR"], 
                        borderwidth=0)
        style.configure('TNotebook.Frame', 
                        background=STYLE_CONFIG["FRAME_COLOR"], 
                        borderwidth=0)
        style.configure('TNotebook.Tab', 
                        font=STYLE_CONFIG["BUTTON_FONT"], 
                        padding=[10, 5],
                        background=STYLE_CONFIG["BG_COLOR"],
                        borderwidth=0)
        style.map('TNotebook.Tab',
                  background=[("selected", STYLE_CONFIG["FRAME_COLOR"])])

    def show_frame(self, PageClass):
        """Destroys the current frame and shows the new one."""
        for widget in self.container.winfo_children():
            widget.destroy()
        
        frame = PageClass(self.container, self)
        frame.pack(fill="both", expand=True)

    def login_success(self, user_id, username):
        self.current_user_id = user_id
        self.current_user_name = username
        self.current_order = {} # Clear cart on login
        self.show_frame(MainApplicationPage)

    def logout(self):
        self.current_user_id = None
        self.current_user_name = None
        self.show_frame(LoginPage)

# --- PAGE 1: LOGIN PAGE ---
class LoginPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='TFrame') # <-- FIX: Added style
        self.controller = controller

        # Center the login box
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self, style='Content.TFrame', padding=40, borderwidth=1, relief="solid")
        main_frame.grid(row=0, column=0)

        ttk.Label(main_frame, text="Restaurant Login", style='Header.TLabel', 
                  background=STYLE_CONFIG["FRAME_COLOR"]).pack(pady=(0, 20))

        # Username
        ttk.Label(main_frame, text="Username", style='Content.TLabel').pack(anchor='w', padx=5)
        self.username_entry = ttk.Entry(main_frame, width=30)
        self.username_entry.pack(pady=(0, 10))

        # Password
        ttk.Label(main_frame, text="Password", style='Content.TLabel').pack(anchor='w', padx=5)
        self.password_entry = ttk.Entry(main_frame, show="*", width=30)
        self.password_entry.pack(pady=(0, 20))

        # Error message
        self.message_label = ttk.Label(main_frame, text="", style='Error.TLabel', 
                                       background=STYLE_CONFIG["FRAME_COLOR"])
        self.message_label.pack(pady=(0, 10))

        # Buttons
        button_frame = ttk.Frame(main_frame, style='Content.TFrame')
        button_frame.pack(fill='x')

        login_button = ttk.Button(button_frame, text="Login", 
                                  command=self.handle_login, style='Primary.TButton')
        login_button.pack(side='left', expand=True, fill='x', padx=(0, 5))

        signup_button = ttk.Button(button_frame, text="Sign Up", 
                                   command=lambda: controller.show_frame(SignUpPage), 
                                   style='Secondary.TButton')
        signup_button.pack(side='right', expand=True, fill='x', padx=(5, 0))

    def handle_login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            self.message_label.config(text="Please enter both username and password.")
            return

        user_id = self.controller.db.validate_user(username, password)
        if user_id:
            self.controller.login_success(user_id, username)
        else:
            self.message_label.config(text="Invalid username or password.")

# --- PAGE 2: SIGN UP PAGE ---
class SignUpPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='TFrame') # <-- FIX: Added style
        self.controller = controller

        # Center the signup box
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self, style='Content.TFrame', padding=40, borderwidth=1, relief="solid")
        main_frame.grid(row=0, column=0)

        ttk.Label(main_frame, text="Create Account", style='Header.TLabel', 
                  background=STYLE_CONFIG["FRAME_COLOR"]).pack(pady=(0, 20))

        # Username
        ttk.Label(main_frame, text="Username", style='Content.TLabel').pack(anchor='w', padx=5)
        self.username_entry = ttk.Entry(main_frame, width=30)
        self.username_entry.pack(pady=(0, 10))

        # Password
        ttk.Label(main_frame, text="Password", style='Content.TLabel').pack(anchor='w', padx=5)
        self.password_entry = ttk.Entry(main_frame, show="*", width=30)
        self.password_entry.pack(pady=(0, 10))
        
        # Confirm Password
        ttk.Label(main_frame, text="Confirm Password", style='Content.TLabel').pack(anchor='w', padx=5)
        self.confirm_entry = ttk.Entry(main_frame, show="*", width=30)
        self.confirm_entry.pack(pady=(0, 20))

        # Error message
        self.message_label = ttk.Label(main_frame, text="", style='Error.TLabel', 
                                       background=STYLE_CONFIG["FRAME_COLOR"])
        self.message_label.pack(pady=(0, 10))

        # Buttons
        button_frame = ttk.Frame(main_frame, style='Content.TFrame')
        button_frame.pack(fill='x')

        signup_button = ttk.Button(button_frame, text="Create Account", 
                                   command=self.handle_signup, style='Primary.TButton')
        signup_button.pack(expand=True, fill='x', pady=(0, 10))

        back_button = ttk.Button(button_frame, text="Back to Login", 
                                 command=lambda: controller.show_frame(LoginPage),
                                 style='Secondary.TButton')
        back_button.pack(expand=True, fill='x')

    def handle_signup(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()

        if not username or not password or not confirm:
            self.message_label.config(text="Please fill all fields.")
            return
        
        if password != confirm:
            self.message_label.config(text="Passwords do not match.")
            return
        
        if len(password) < 6:
             self.message_label.config(text="Password must be at least 6 characters.")
             return

        # Try to create the user
        result = self.controller.db.create_user(username, password)
        
        if result == "SUCCESS":
            messagebox.showinfo("Success", "Account created successfully! Please log in.")
            self.controller.show_frame(LoginPage)
        elif result == "DUPLICATE":
            self.message_label.config(text="Username already exists. Try another.")
        else: # result == "OTHER_ERROR"
            self.message_label.config(text="A database error occurred.")
            messagebox.showerror("Database Error", 
                                 "An unexpected database error occurred. "
                                 f"Details: {result}\n\n"
                                 "Please check the console for more info. "
                                 "This could be a permissions problem with your database user.")

# --- PAGE 3: MAIN APPLICATION (MENU, BILL, FEEDBACK) ---
class MainApplicationPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='TFrame') # <-- This line is correct
        self.controller = controller

        # Header
        header_frame = ttk.Frame(self, padding=(0, 10), style='TFrame') # <-- FIX: Added style='TFrame'
        header_frame.pack(fill='x')

        welcome_text = f"Welcome, {self.controller.current_user_name}!"
        ttk.Label(header_frame, text=welcome_text, style='Header.TLabel').pack(side='left')

        logout_button = ttk.Button(header_frame, text="Logout", 
                                   command=controller.logout, style='Secondary.TButton')
        logout_button.pack(side='right')

        # Notebook (Tabs)
        notebook = ttk.Notebook(self, style='TNotebook') # <-- FIX: Added style='TNotebook'
        notebook.pack(fill='both', expand=True, pady=10)

        # Create the tab frames
        self.menu_frame = MenuFrame(notebook, controller)
        self.bill_frame = BillFrame(notebook, controller)
        self.feedback_frame = FeedbackFrame(notebook, controller)

        notebook.add(self.menu_frame, text='Menu')
        notebook.add(self.bill_frame, text='Bill Calculator')
        notebook.add(self.feedback_frame, text='Feedback')

        # When the Bill tab is clicked, update the view
        notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

    def on_tab_change(self, event):
        # Check if the selected tab is the BillFrame
        selected_tab_index = event.widget.index(event.widget.select())
        if selected_tab_index == 1: # Index 1 is the BillFrame
            self.bill_frame.update_bill()

# --- Tab 1: Menu Frame ---
class MenuFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='Content.TFrame', padding=20)
        self.controller = controller
        self.menu_widgets = [] # To store refs to checkboxes, spinboxes, etc.

        ttk.Label(self, text="Today's Menu", style='Header.TLabel', 
                  background=STYLE_CONFIG["FRAME_COLOR"]).pack(pady=(0, 10))
        
        # Create the main scrollable frame
        self.scroll_frame = ScrollableFrame(self, style='Content.TFrame') # <-- THIS IS THE FIX
        self.scroll_frame.pack(fill='both', expand=True)

        # The 'inner' frame inside ScrollableFrame is where we add widgets
        self.inner_frame = self.scroll_frame.scrollable_frame

        # Controls for adding to order
        controls_frame = ttk.Frame(self, style='Content.TFrame')
        controls_frame.pack(fill='x', pady=10)

        add_button = ttk.Button(controls_frame, text="Add Selected to Order", 
                                command=self.add_to_order, style='Primary.TButton')
        add_button.pack(side='left', padx=10)

        reset_button = ttk.Button(controls_frame, text="Reset Selections", 
                                  command=self.reset_selections, style='Secondary.TButton')
        reset_button.pack(side='left', padx=10)
        
        self.add_message_label = ttk.Label(controls_frame, text="", style='Content.TLabel')
        self.add_message_label.pack(side='left')

        # self.load_menu() # <-- This was the original, buggy line
        
        # --- THIS IS THE FIX ---
        # Wrap the menu load in a try-except to prevent any
        # potential database error from crashing the entire UI
        # during initialization. This stops the "blank screen" bug.
        try:
            self.load_menu()
        except Exception as e:
            # Print the error to the console for debugging
            print(f"CRITICAL: Failed to load menu: {e}")
            # Display a visible error message on the menu tab
            # This ensures the frame is not blank.
            ttk.Label(self.inner_frame, 
                      text=f"Error loading menu:\n{e}\n\n"
                           "Please check database connection and terminal.", 
                      style='Content.TLabel', 
                      padding=20,
                      font=STYLE_CONFIG["BODY_FONT"],
                      background=STYLE_CONFIG["FRAME_COLOR"],
                      foreground="red").pack()
        # --- END OF FIX ---

    def load_menu(self):
        # Clear any existing widgets
        for widget in self.inner_frame.winfo_children():
            widget.destroy()
        self.menu_widgets = []
            
        menu_items = self.controller.db.get_menu_items()
        
        if not menu_items:
            # --- THIS IS THE FIX ---
            # If no items, show a message so the frame doesn't collapse
            ttk.Label(self.inner_frame, 
                      text="No menu items found.\nCheck database connection and setup.", 
                      style='Content.TLabel', 
                      padding=20
                      # font=... (Remove this line)
                      ).pack()
            # --- END OF FIX ---
            return # Don't proceed to the rest of the function

        for item in menu_items:
            # Create a frame for each menu item
            item_frame = ttk.Frame(self.inner_frame, style='Content.TFrame', padding=10, relief="solid", borderwidth=1)
            item_frame.pack(fill='x', expand=True, pady=5, padx=5)

            # --- Left side: Checkbox, Name, Description ---
            left_frame = ttk.Frame(item_frame, style='Content.TFrame')
            left_frame.pack(side='left', fill='x', expand=True, padx=(0, 20))

            # --- Right side: Price, Quantity ---
            right_frame = ttk.Frame(item_frame, style='Content.TFrame')
            right_frame.pack(side='right', fill='none')

            # Checkbox variable
            check_var = tk.BooleanVar()
            
            # Checkbox and Name
            # --- FIX 3: Use the new style directly ---
            name_check = ttk.Checkbutton(left_frame, text=item['name'], variable=check_var, style='MenuName.TCheckbutton')
            # name_check.configure(font=STYLE_CONFIG["BUTTON_FONT"]) # <-- Delete this line
            name_check.pack(anchor='w')

            # Description
            desc_label = ttk.Label(left_frame, text=item['description'], style='Content.TLabel', wraplength=400, justify='left')
            desc_label.pack(anchor='w', pady=(5,0))

            # Price
            # --- FIX 4: Use the new style directly ---
            price_label = ttk.Label(right_frame, text=f"${item['price']:.2f}", style='MenuPrice.TLabel')
            # price_label.configure(font=STYLE_CONFIG["BUTTON_FONT"]) # <-- Delete this line
            price_label.pack(anchor='e')

            # Quantity Spinbox
            quantity_spinbox = ttk.Spinbox(right_frame, from_=1, to=10, width=5)
            quantity_spinbox.set(1)
            quantity_spinbox.pack(anchor='e', pady=(5,0))

            # Store all the widgets and data for this item
            self.menu_widgets.append({
                'check_var': check_var,
                'spinbox': quantity_spinbox,
                'item_data': item
            })

    def add_to_order(self):
        cart = self.controller.current_order
        items_added_count = 0
        
        for widget_set in self.menu_widgets:
            if widget_set['check_var'].get(): # If the box is checked
                items_added_count += 1
                try:
                    quantity = int(widget_set['spinbox'].get())
                    if quantity <= 0:
                        raise ValueError
                except ValueError:
                    quantity = 1 # Default to 1 if invalid
                
                item = widget_set['item_data']
                item_id = item['item_id']
                
                # Add to the cart
                if item_id in cart:
                    cart[item_id]['quantity'] += quantity
                else:
                    cart[item_id] = {
                        'name': item['name'],
                        'price': float(item['price']),
                        'quantity': quantity,
                        'item_id': item_id
                    }

        if items_added_count > 0:
            self.add_message_label.config(text=f"Added {items_added_count} item(s) to order.", foreground='green')
            # Reset the menu after ordering
            self.reset_selections()
        else:
            self.add_message_label.config(text="Please check an item to add.", foreground='red')

        # Clear message after 3 seconds
        self.after(3000, lambda: self.add_message_label.config(text=""))
    
    def reset_selections(self):
        """Unchecks all boxes and resets spinboxes to 1."""
        for widget_set in self.menu_widgets:
            widget_set['check_var'].set(False)
            widget_set['spinbox'].set(1)
        
        self.add_message_label.config(text="")


# --- Tab 2: Bill Frame ---
class BillFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='Content.TFrame', padding=20)
        self.controller = controller

        ttk.Label(self, text="Your Current Order", style='Header.TLabel', 
                  background=STYLE_CONFIG["FRAME_COLOR"]).pack(pady=(0, 10))

        # Frame for Treeview
        tree_frame = ttk.Frame(self, style='Content.TFrame')
        tree_frame.pack(fill='both', expand=True)

        # Treeview to display order
        cols = ('Item', 'Quantity', 'Unit Price', 'Total')
        self.tree = ttk.Treeview(tree_frame, columns=cols, show='headings', height=10)
        
        for col in cols:
            self.tree.heading(col, text=col)
            
        self.tree.column('Item', width=200)
        self.tree.column('Quantity', width=80, anchor='center')
        self.tree.column('Unit Price', width=100, anchor='e')
        self.tree.column('Total', width=100, anchor='e')

        self.tree.pack(fill='both', expand=True)
        
        # Total Label
        self.total_label = ttk.Label(self, text="Total: $0.00", style='Header.TLabel', 
                                     background=STYLE_CONFIG["FRAME_COLOR"])
        self.total_label.pack(anchor='e', pady=10)

        # Controls
        controls_frame = ttk.Frame(self, style='Content.TFrame')
        controls_frame.pack(fill='x', pady=10)

        remove_button = ttk.Button(controls_frame, text="Remove Selected Item", 
                                   command=self.remove_item, style='Secondary.TButton')
        remove_button.pack(side='left')

        clear_button = ttk.Button(controls_frame, text="Clear Order", 
                                  command=self.clear_order, style='Secondary.TButton')
        clear_button.pack(side='left', padx=10)
        
        confirm_button = ttk.Button(controls_frame, text="Confirm and Pay", 
                                    command=self.confirm_order, style='Primary.TButton')
        confirm_button.pack(side='right')

    def update_bill(self):
        # Clear existing items
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        cart = self.controller.current_order
        total_bill = 0.0

        for item_id, details in cart.items():
            total_item_price = details['price'] * details['quantity']
            total_bill += total_item_price
            
            self.tree.insert("", "end", values=(
                details['name'],
                details['quantity'],
                f"${details['price']:.2f}",
                f"${total_item_price:.2f}"
            ), iid=item_id) # Use item_id as iid
            
        self.total_label.config(text=f"Total: ${total_bill:.2f}")

    def remove_item(self):
        selected_iid = self.tree.focus()
        if not selected_iid:
            messagebox.showwarning("No Selection", "Please select an item to remove.")
            return
        
        # selected_iid is the item_id we set (as an int)
        item_id_to_remove = int(selected_iid)
        if item_id_to_remove in self.controller.current_order:
            del self.controller.current_order[item_id_to_remove]
            self.update_bill()

    def clear_order(self):
        if messagebox.askyesno("Clear Order", "Are you sure you want to clear the entire order?"):
            self.controller.current_order = {}
            self.update_bill()
            
    def confirm_order(self):
        cart = self.controller.current_order
        if not cart:
            messagebox.showwarning("Empty Order", "Your order is empty.")
            return

        total_bill = sum(item['price'] * item['quantity'] for item in cart.values())
        
        # Prepare items list for DB
        items_for_db = list(cart.values())
        user_id = self.controller.current_user_id
        
        if self.controller.db.create_order(user_id, total_bill, items_for_db):
            messagebox.showinfo("Order Confirmed", 
                                f"Your order for ${total_bill:.2f} has been confirmed!")
            self.clear_order()
        else:
            messagebox.showerror("Order Failed", "There was an error saving your order. Please try again.")

# --- Tab 3: Feedback Frame ---
class FeedbackFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='Content.TFrame', padding=20)
        self.controller = controller

        ttk.Label(self, text="We Value Your Feedback!", style='Header.TLabel', 
                  background=STYLE_CONFIG["FRAME_COLOR"]).pack(pady=(0, 20))

        form_frame = ttk.Frame(self, style='Content.TFrame')
        form_frame.pack(fill='x')
        
        # Rating
        ttk.Label(form_frame, text="Rating (1-5):", style='Content.TLabel').pack(anchor='w')
        self.rating_var = tk.IntVar(value=5)
        rating_scale = ttk.Scale(form_frame, from_=1, to=5, variable=self.rating_var,
                                 orient='horizontal', length=300,
                                 command=lambda v: self.rating_label.config(text=f"{int(float(v))}/5"))
        rating_scale.pack(fill='x', pady=5)
        
        self.rating_label = ttk.Label(form_frame, text="5/5", style='Content.TLabel')
        self.rating_label.pack()

        # Comments
        ttk.Label(form_frame, text="Comments:", style='Content.TLabel').pack(anchor='w', pady=(10, 5))
        self.comments_text = tk.Text(form_frame, height=10, width=60, 
                                     font=STYLE_CONFIG["BODY_FONT"], 
                                     relief='solid', borderwidth=1,
                                     padx=5, pady=5)
        self.comments_text.pack(fill='both', expand=True, pady=(0, 20))

        # Submit Button
        submit_button = ttk.Button(form_frame, text="Submit Feedback", 
                                   command=self.submit_feedback, style='Primary.TButton')
        submit_button.pack()

    def submit_feedback(self):
        rating = self.rating_var.get()
        comments = self.comments_text.get("1.0", "end-1c").strip() # Get text
        
        if not comments:
            messagebox.showwarning("Empty Feedback", "Please leave a comment.")
            return
            
        user_id = self.controller.current_user_id
        
        if self.controller.db.submit_feedback(user_id, rating, comments):
            messagebox.showinfo("Thank You!", "Your feedback has been submitted.")
            # Clear the form
            self.rating_var.set(5)
            self.rating_label.config(text="5/5")
            self.comments_text.delete("1.0", "end")
        else:
            messagebox.showerror("Error", "Could not submit feedback. Please try again.")

# --- RUN THE APPLICATION ---
if __name__ == "__main__":
    try:
        # 1. Install the required library if you haven't:
        # pip install mysql-connector-python
        
        # 2. Ensure your MySQL server is running.
        
        # 3. Update DB_CONFIG at the top of this file.
        
        db = DatabaseManager(DB_CONFIG)
        app = RestaurantApp(db)
        app.mainloop()
    except ImportError:
        print("Error: 'mysql-connector-python' not found.")
        print("Please install it by running: pip install mysql-connector-python")
        messagebox.showerror("Missing Library", 
                             "The 'mysql-connector-python' library is required.\n"
                             "Please install it using: \npip install mysql-connector-python")
    except Exception as e:
        print(f"Application failed: {e}")
        messagebox.showerror("Fatal Error", f"Application failed to start: {e}")
