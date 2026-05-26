import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import re
from pathlib import Path
from collections import defaultdict
import subprocess
import os


class SpellFixerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SpellFix")
        self.root.geometry("1400x800")

        self.typos = defaultdict(list)
        self.fixed_items = {}  # Track fixed/skipped items: (typo, file, line) -> status
        self.report_path = tk.StringVar(value="report.txt")
        self.repo_path = tk.StringVar(value=".")
        self.max_issues = tk.IntVar(value=5000)
        self.context_lines = tk.IntVar(value=15)
        self.status_text = tk.StringVar(value="Ready")
        self.ignored_patterns = self.load_gitignore()
        self.sort_option = tk.StringVar(value="alphabetical")
        self.selected_typo = None
        self.selected_occurrence = None

        self.setup_ui()
        self.root.after(100, self.load_report_with_splash)

    def update_status(self, message):
        """Update status bar"""
        self.status_text.set(message)
        self.root.update_idletasks()

    def load_gitignore(self):
        """Load patterns from .gitignore files"""
        self.update_status("Loading gitignore patterns...")
        patterns = []
        repo_path = Path(self.repo_path.get())
        for gitignore in repo_path.rglob(".gitignore"):
            try:
                with open(gitignore, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except:
                pass
        self.update_status(f"Loaded {len(patterns)} gitignore patterns")
        return patterns

    def is_ignored(self, filepath):
        """Check if filepath matches any gitignore pattern"""
        filepath = filepath.replace("\\", "/")
        for pattern in self.ignored_patterns:
            if "*" in pattern:
                import fnmatch
                if fnmatch.fnmatch(filepath, pattern):
                    return True
            elif pattern in filepath:
                return True
        return False

    def apply_case_pattern(self, original, replacement):
        """Apply the case pattern of original to replacement"""
        if not original or not replacement:
            return replacement

        # All uppercase
        if original.isupper():
            return replacement.upper()

        # All lowercase
        if original.islower():
            return replacement.lower()

        # Title case (first letter uppercase)
        if original[0].isupper() and len(original) > 1 and original[1:].islower():
            return replacement[0].upper() + replacement[1:].lower()

        # Mixed case - return as-is
        return replacement

    def mark_in_report(self, typo, filepath, line_num, mark_type="fixed"):
        """Mark an item as fixed or skipped in the report file"""
        try:
            report_file = self.report_path.get()
            marker = f"[{mark_type.upper()}]"

            # Read report
            with open(report_file, "r", encoding="utf-16", errors="ignore") as f:
                lines = f.readlines()

            # Find and mark the matching line
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if line_stripped.startswith("[FIXED]") or line_stripped.startswith("[SKIPPED]"):
                    continue

                # Check if this is the line we're looking for
                match = re.match(r"\.\\(.+?):(\d+):\s+(.+?)\s+=+>\s+(.+)", line_stripped)
                if match:
                    file_in_report = match.group(1).replace("\\", "/")
                    line_in_report = int(match.group(2))
                    typo_in_report = match.group(3).strip()

                    if file_in_report == filepath and line_in_report == line_num and typo_in_report == typo:
                        # Mark this line
                        lines[i] = f"{marker} {line_stripped}\n"
                        break

            # Write back
            with open(report_file, "w", encoding="utf-16", errors="ignore") as f:
                f.writelines(lines)

        except Exception as e:
            print(f"Error marking report: {e}")

    def load_report(self):
        """Parse the report.txt file with issue limit"""
        try:
            self.update_status("Clearing typo list...")
            self.fixed_items.clear()
            report_file = self.report_path.get()
            if not Path(report_file).exists():
                messagebox.showerror("Error", f"Report file not found: {report_file}")
                self.update_status("Error: Report file not found")
                return

            self.update_status("Loading report file...")
            max_issues = self.max_issues.get()
            issue_count = 0
            fixed_count = 0
            skipped_count = 0

            with open(report_file, "r", encoding="utf-16", errors="ignore") as f:
                for line in f:
                    if issue_count >= max_issues:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    # Check if already marked as fixed or skipped
                    is_fixed = line.startswith("[FIXED]")
                    is_skipped = line.startswith("[SKIPPED]")

                    if is_fixed or is_skipped:
                        # Extract info from marked line
                        line_to_parse = line[8:] if is_fixed else line[10:]  # Remove marker
                        match = re.match(r"\.\\(.+?):(\d+):\s+(.+?)\s+=+>\s+(.+)", line_to_parse)
                        if match:
                            filepath = match.group(1).replace("\\", "/")
                            line_num = int(match.group(2))
                            typo = match.group(3).strip()
                            status = "fixed" if is_fixed else "skipped"
                            self.fixed_items[(typo, filepath, line_num)] = status
                            if is_fixed:
                                fixed_count += 1
                            else:
                                skipped_count += 1
                        continue

                    match = re.match(r"\.\\(.+?):(\d+):\s+(.+?)\s+=+>\s+(.+)", line)
                    if match:
                        filepath = match.group(1).replace("\\", "/")
                        if self.is_ignored(filepath):
                            continue

                        line_num = int(match.group(2))
                        typo = match.group(3).strip()
                        corrections = [c.strip() for c in match.group(4).split(",")]

                        self.typos[typo].append({
                            "file": filepath,
                            "line": line_num,
                            "corrections": corrections,
                            "status": "pending"
                        })
                        issue_count += 1

                        if issue_count % 500 == 0:
                            self.update_status(f"Loaded {issue_count} issues...")

            status_msg = f"Loaded {len(self.typos)} unique typos ({issue_count} pending, {fixed_count} fixed, {skipped_count} skipped)"
            self.update_status(status_msg)
            self.refresh_typo_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load report: {e}")
            self.update_status("Error loading report")

    def setup_ui(self):
        """Setup the UI layout"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Report file selector row
        report_frame = ttk.Frame(main_frame)
        report_frame.pack(fill=tk.X, pady=5)

        ttk.Label(report_frame, text="Report:").pack(side=tk.LEFT, padx=5)
        self.report_entry = ttk.Entry(report_frame, textvariable=self.report_path, width=50)
        self.report_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(report_frame, text="Browse", command=self.select_report_file).pack(side=tk.LEFT, padx=2)

        # Repository folder selector row
        repo_frame = ttk.Frame(main_frame)
        repo_frame.pack(fill=tk.X, pady=5)

        ttk.Label(repo_frame, text="Repository Folder:").pack(side=tk.LEFT, padx=5)
        self.repo_entry = ttk.Entry(repo_frame, textvariable=self.repo_path, width=50)
        self.repo_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(repo_frame, text="Browse", command=self.select_repo_folder).pack(side=tk.LEFT, padx=2)

        # Options row
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=5)

        ttk.Label(toolbar, text="Sort by:").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(toolbar, text="Alphabetical", variable=self.sort_option,
                       value="alphabetical", command=self.refresh_typo_list).pack(side=tk.LEFT)
        ttk.Radiobutton(toolbar, text="# Occurrences", variable=self.sort_option,
                       value="count", command=self.refresh_typo_list).pack(side=tk.LEFT)

        ttk.Label(toolbar, text="  Max Issues:").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(toolbar, from_=100, to=100000, textvariable=self.max_issues, width=8,
                   command=self.on_settings_change).pack(side=tk.LEFT, padx=2)

        ttk.Label(toolbar, text="  Context Lines:").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(toolbar, from_=5, to=200, textvariable=self.context_lines, width=6).pack(side=tk.LEFT, padx=2)

        # Three-panel layout with resizable columns
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel: Typos list
        left_panel = ttk.LabelFrame(paned, text="Typos")
        paned.add(left_panel, weight=1)

        left_frame = ttk.Frame(left_panel)
        left_frame.pack(fill=tk.BOTH, expand=True)

        self.typo_listbox = tk.Listbox(left_frame, height=30)
        self.typo_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.typo_listbox.bind("<<ListboxSelect>>", self.on_typo_select)

        scrollbar_left = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.typo_listbox.yview)
        scrollbar_left.pack(side=tk.RIGHT, fill=tk.Y)
        self.typo_listbox.config(yscrollcommand=scrollbar_left.set)

        # Middle panel: Occurrences
        middle_panel = ttk.LabelFrame(paned, text="Occurrences")
        paned.add(middle_panel, weight=1)

        middle_frame = ttk.Frame(middle_panel)
        middle_frame.pack(fill=tk.BOTH, expand=True)

        self.occurrence_listbox = tk.Listbox(middle_frame, height=30)
        self.occurrence_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.occurrence_listbox.bind("<<ListboxSelect>>", self.on_occurrence_select)

        scrollbar_middle = ttk.Scrollbar(middle_frame, orient=tk.VERTICAL, command=self.occurrence_listbox.yview)
        scrollbar_middle.pack(side=tk.RIGHT, fill=tk.Y)
        self.occurrence_listbox.config(yscrollcommand=scrollbar_middle.set)

        # Right panel: Code view and controls
        right_panel = ttk.LabelFrame(paned, text="Code Preview & Fix")
        paned.add(right_panel, weight=1)

        # Code display
        self.code_text = scrolledtext.ScrolledText(right_panel, height=25, width=50, wrap=tk.WORD)
        self.code_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Control panel at bottom of right panel
        control_frame = ttk.Frame(right_panel)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(control_frame, text="Correction:").pack(side=tk.LEFT, padx=5)

        # Status label for multiple corrections (warning)
        self.correction_label = ttk.Label(control_frame, text="", foreground="red")
        self.correction_label.pack(side=tk.LEFT, padx=5)

        self.correction_var = tk.StringVar()
        self.correction_combo = ttk.Combobox(control_frame, textvariable=self.correction_var, state="readonly")
        self.correction_combo.pack(side=tk.LEFT, padx=5)

        ttk.Button(control_frame, text="Replace Here", command=self.replace_here).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Replace in All Files", command=self.replace_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Skip", command=self.skip_occurrence).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Skip All", command=self.skip_all).pack(side=tk.LEFT, padx=2)

        # Status bar at bottom
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)

        self.status_label = ttk.Label(status_frame, textvariable=self.status_text, relief=tk.SUNKEN)
        self.status_label.pack(fill=tk.X)

    def refresh_typo_list(self):
        """Refresh the typo list based on sort option"""
        self.typo_listbox.delete(0, tk.END)

        if self.sort_option.get() == "alphabetical":
            sorted_typos = sorted(self.typos.keys())
        else:  # count
            sorted_typos = sorted(self.typos.keys(), key=lambda t: len(self.typos[t]), reverse=True)

        for typo in sorted_typos:
            count = len(self.typos[typo])
            self.typo_listbox.insert(tk.END, f"{typo} ({count})")

    def on_typo_select(self, event):
        """Handle typo selection"""
        selection = self.typo_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if self.sort_option.get() == "alphabetical":
            sorted_typos = sorted(self.typos.keys())
        else:
            sorted_typos = sorted(self.typos.keys(), key=lambda t: len(self.typos[t]), reverse=True)

        self.selected_typo = sorted_typos[idx]
        self.refresh_occurrence_list()

        # Automatically select first occurrence
        if self.occurrence_listbox.size() > 0:
            self.occurrence_listbox.selection_set(0)
            self.on_occurrence_select(None)
        else:
            self.clear_code_view()

    def refresh_occurrence_list(self):
        """Refresh the occurrence list for selected typo"""
        self.occurrence_listbox.delete(0, tk.END)

        if not self.selected_typo:
            return

        for i, occ in enumerate(self.typos[self.selected_typo]):
            # Check if this occurrence is marked as fixed or skipped
            key = (self.selected_typo, occ['file'], occ['line'])
            status = self.fixed_items.get(key, "pending")

            if status == "fixed":
                display = f"✓ {occ['file']}:{occ['line']}"
                color = "green"
            elif status == "skipped":
                display = f"⊘ {occ['file']}:{occ['line']}"
                color = "orange"
            else:
                display = f"  {occ['file']}:{occ['line']}"
                color = "black"

            self.occurrence_listbox.insert(tk.END, display)
            self.occurrence_listbox.itemconfig(i, fg=color)

    def on_occurrence_select(self, event):
        """Handle occurrence selection"""
        selection = self.occurrence_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        self.selected_occurrence = self.typos[self.selected_typo][idx]
        self.load_code_view()
        self.update_correction_options()

    def load_code_view(self):
        """Load and display code around the typo"""
        if not self.selected_occurrence:
            return

        filepath = Path(self.repo_path.get()) / self.selected_occurrence["file"]
        line_num = self.selected_occurrence["line"]

        try:
            if not filepath.exists():
                self.code_text.config(state=tk.NORMAL)
                self.code_text.delete(1.0, tk.END)
                self.code_text.insert(tk.END, f"File not found:\n{filepath}")
                self.code_text.config(state=tk.DISABLED)
                return

            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            context = self.context_lines.get()
            start = max(0, line_num - context - 1)
            end = min(len(lines), line_num + context)

            self.code_text.config(state=tk.NORMAL)
            self.code_text.delete(1.0, tk.END)

            for i in range(start, end):
                line_content = lines[i].rstrip("\n")
                prefix = ">>> " if i + 1 == line_num else "    "
                self.code_text.insert(tk.END, f"{prefix}{i + 1}: {line_content}\n")

                # Highlight the typo line
                if i + 1 == line_num:
                    start_idx = self.code_text.search(self.selected_typo, f"{i + 1 - start + 1}.0", tk.END, nocase=False)
                    if start_idx:
                        end_idx = f"{start_idx.split('.')[0]}.{int(start_idx.split('.')[1]) + len(self.selected_typo)}"
                        self.code_text.tag_add("typo", start_idx, end_idx)

            self.code_text.tag_config("typo", background="yellow", foreground="red")
            self.code_text.config(state=tk.DISABLED)
        except Exception as e:
            self.code_text.config(state=tk.NORMAL)
            self.code_text.delete(1.0, tk.END)
            self.code_text.insert(tk.END, f"Error loading file: {e}")
            self.code_text.config(state=tk.DISABLED)

    def update_correction_options(self):
        """Update correction dropdown"""
        if not self.selected_occurrence:
            return

        corrections = self.selected_occurrence["corrections"]
        self.correction_combo["values"] = corrections

        if len(corrections) == 1:
            self.correction_combo.current(0)
            self.correction_label.config(text="")
        else:
            self.correction_combo.current(0)
            self.correction_label.config(text=f"{len(corrections)} possibilities", foreground="red")

    def clear_code_view(self):
        """Clear the code view"""
        self.code_text.config(state=tk.NORMAL)
        self.code_text.delete(1.0, tk.END)
        self.code_text.config(state=tk.DISABLED)
        self.correction_combo["values"] = []
        self.correction_label.config(text="")

    def skip_occurrence(self):
        """Mark current occurrence as skipped"""
        if not self.selected_occurrence:
            messagebox.showwarning("Warning", "Please select an occurrence first")
            return

        try:
            self.update_status(f"Skipping '{self.selected_typo}'...")

            # Mark as skipped in report
            self.mark_in_report(self.selected_typo, self.selected_occurrence["file"], self.selected_occurrence["line"], "skipped")

            # Remove this occurrence from the list
            self.typos[self.selected_typo].pop(self.occurrence_listbox.curselection()[0])
            if not self.typos[self.selected_typo]:
                del self.typos[self.selected_typo]

            self.update_status("Marked as [SKIPPED]")
            self.refresh_typo_list()
            self.clear_code_view()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to skip: {e}")
            self.update_status("Error marking as skipped")

    def skip_all(self):
        """Mark all occurrences of current typo as skipped"""
        if not self.selected_typo:
            messagebox.showwarning("Warning", "Please select a typo first")
            return

        total = len(self.typos[self.selected_typo])

        try:
            self.update_status(f"Skipping all {total} occurrences...")

            # Mark all occurrences as skipped
            for occurrence in self.typos[self.selected_typo]:
                self.mark_in_report(self.selected_typo, occurrence["file"], occurrence["line"], "skipped")

            # Remove all occurrences of this typo
            if self.selected_typo in self.typos:
                del self.typos[self.selected_typo]

            self.update_status(f"Skipped all {total} occurrences, marked as [SKIPPED]")
            self.refresh_typo_list()
            self.clear_code_view()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to skip all: {e}")
            self.update_status("Error during bulk skip")

    def replace_here(self):
        """Replace typo in current file only"""
        if not self.selected_occurrence or not self.correction_var.get():
            messagebox.showwarning("Warning", "Please select a typo and correction first")
            return

        filepath = Path(self.repo_path.get()) / self.selected_occurrence["file"]
        line_num = self.selected_occurrence["line"]
        correction = self.correction_var.get()

        try:
            self.update_status(f"Replacing '{self.selected_typo}' with '{correction}'...")
            if not filepath.exists():
                messagebox.showerror("Error", f"File not found:\n{filepath}")
                return

            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            if line_num > len(lines):
                messagebox.showerror("Error", f"Line {line_num} not found in file")
                return

            # Find and replace with smart capitalization
            line_content = lines[line_num - 1]
            replaced = False

            # Try to find the typo with any case variant
            for match in re.finditer(re.escape(self.selected_typo), line_content, re.IGNORECASE):
                found_typo = match.group()
                corrected = self.apply_case_pattern(found_typo, correction)
                line_content = line_content[:match.start()] + corrected + line_content[match.end():]
                replaced = True
                break

            if replaced:
                lines[line_num - 1] = line_content
            else:
                messagebox.showwarning("Warning", f"Typo '{self.selected_typo}' not found in line {line_num}")
                return

            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(lines)

            messagebox.showinfo("Success", f"Replaced in {filepath}:{line_num}")

            # Mark as fixed in report
            self.mark_in_report(self.selected_typo, self.selected_occurrence["file"], line_num, "fixed")

            # Remove this occurrence from the list
            self.typos[self.selected_typo].pop(self.occurrence_listbox.curselection()[0])
            if not self.typos[self.selected_typo]:
                del self.typos[self.selected_typo]

            self.update_status("Replacement complete - marked as [FIXED]")
            self.refresh_typo_list()
            self.clear_code_view()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to replace: {e}")
            self.update_status("Error during replacement")

    def replace_all(self):
        """Replace typo in all files"""
        if not self.selected_typo or not self.correction_var.get():
            messagebox.showwarning("Warning", "Please select a typo and correction first")
            return

        correction = self.correction_var.get()
        count = 0
        total = len(self.typos[self.selected_typo])

        try:
            self.update_status(f"Replacing all {total} occurrences...")
            occurrences_to_mark = []

            for i, occurrence in enumerate(self.typos[self.selected_typo]):
                filepath = Path(self.repo_path.get()) / occurrence["file"]
                line_num = occurrence["line"]

                try:
                    if not filepath.exists():
                        continue

                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    if line_num <= len(lines):
                        line_content = lines[line_num - 1]

                        # Find and replace with smart capitalization
                        for match in re.finditer(re.escape(self.selected_typo), line_content, re.IGNORECASE):
                            found_typo = match.group()
                            corrected = self.apply_case_pattern(found_typo, correction)
                            line_content = line_content[:match.start()] + corrected + line_content[match.end():]
                            break

                        lines[line_num - 1] = line_content

                        with open(filepath, "w", encoding="utf-8") as f:
                            f.writelines(lines)

                        count += 1
                        occurrences_to_mark.append(occurrence)

                    if (i + 1) % 10 == 0:
                        self.update_status(f"Replaced {count}/{total}...")
                except Exception:
                    pass

            # Mark all replaced items in report
            for occurrence in occurrences_to_mark:
                self.mark_in_report(self.selected_typo, occurrence["file"], occurrence["line"], "fixed")

            messagebox.showinfo("Success", f"Replaced {count} occurrences of '{self.selected_typo}'")

            # Remove all occurrences of this typo
            if self.selected_typo in self.typos:
                del self.typos[self.selected_typo]

            self.update_status(f"Replacement complete: {count} files modified, marked as [FIXED]")
            self.refresh_typo_list()
            self.clear_code_view()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to replace all: {e}")
            self.update_status("Error during bulk replacement")

    def select_report_file(self):
        """Open file dialog to select report file"""
        filepath = filedialog.askopenfilename(
            title="Select Report File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            self.report_path.set(filepath)
            self.typos.clear()
            self.root.after(100, self.load_report_with_splash)

    def select_repo_folder(self):
        """Open folder dialog to select repository folder"""
        folder = filedialog.askdirectory(title="Select Repository Folder")
        if folder:
            self.repo_path.set(folder)
            self.ignored_patterns = self.load_gitignore()
            self.typos.clear()
            self.root.after(100, self.load_report_with_splash)

    def on_settings_change(self):
        """Handle max issues change"""
        self.typos.clear()
        self.root.after(100, self.load_report_with_splash)

    def load_report_with_splash(self):
        """Show loading screen while parsing report"""
        loading_win = tk.Toplevel(self.root)
        loading_win.title("Loading")
        loading_win.geometry("300x100")
        loading_win.resizable(False, False)
        loading_win.transient(self.root)
        loading_win.grab_set()

        frame = ttk.Frame(loading_win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Loading report...", font=("", 12)).pack(pady=10)
        progress = ttk.Progressbar(frame, mode='indeterminate')
        progress.pack(fill=tk.X, pady=10)
        progress.start()

        loading_win.update()
        self.load_report()
        loading_win.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SpellFixerApp(root)
    root.mainloop()
