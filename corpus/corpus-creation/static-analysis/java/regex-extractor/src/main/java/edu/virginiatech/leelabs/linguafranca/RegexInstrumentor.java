package edu.virginiatech.leelabs.linguafranca;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseException;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import com.github.javaparser.ast.visitor.ModifierVisitor;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.NodeList;

import com.github.javaparser.symbolsolver.model.resolution.TypeSolver;
import com.github.javaparser.symbolsolver.*;
import com.github.javaparser.symbolsolver.resolution.typesolvers.*;
import com.github.javaparser.resolution.declarations.ResolvedValueDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.types.ResolvedType;
import com.github.javaparser.resolution.UnsolvedSymbolException;

import com.google.common.base.Strings;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;

import java.util.regex.Pattern;
import java.util.regex.Matcher;

import java.util.Optional;
import java.util.List;
import java.util.ArrayList;

import com.google.gson.Gson;

public class RegexInstrumentor {
  private static String codeTemplate;

  private static String getTypeName(Expression expr) {
    return expr.getClass().getName();
  }

  /**
   * @returns: String or null
   */
  private static String getFirstArgIfLiteralString(NodeList<Expression> methodCallArgs) {
    Expression arg = methodCallArgs.get(0);
    if (arg.isStringLiteralExpr()) {
      StringLiteralExpr patternStr = arg.asStringLiteralExpr();
      return patternStr.getValue();
    } else {
      return null;
    }
  }

  private static boolean isScopedMethodCall(MethodCallExpr expr) {
    Optional<Expression> scopeName = expr.getScope();
    return scopeName.isPresent();
  }

  private static boolean isStringType(NameExpr nameExpr) {
    try {
      ResolvedValueDeclaration rvd = nameExpr.resolve();
      ResolvedType type = rvd.getType();
      if (type.describe().equals("java.lang.String")) {
        return true;
      }
    } catch (Exception e) {
      return false;
    }
    return false;
  }

  private static boolean isStringType(MethodCallExpr mcExpr) {
    try {
      ResolvedMethodDeclaration rmd = mcExpr.resolve();
      ResolvedType type = rmd.getReturnType();
      if (type.describe().equals("java.lang.String")) {
        return true;
      }
    } catch (Exception e) {
      return false;
    }
    return false;
  }

  private static boolean isMethodCallInStringScope(MethodCallExpr expr) {
    if (isScopedMethodCall(expr)) {
      Expression scope = expr.getScope().get();
      if (scope.isStringLiteralExpr()) {
        // If the scope is a string literal, then we are in String scope by definition
        return true;
      } else if (scope.isNameExpr()) {
        NameExpr ne_scope = scope.asNameExpr();
        return isStringType(ne_scope);
      } else if (scope.isMethodCallExpr()) {
        MethodCallExpr mce_scope = scope.asMethodCallExpr();
        return isStringType(mce_scope);
      } else {
        return false;
      }
    }
    return false;
  }

  private static boolean isMethodCallInPatternScope(MethodCallExpr expr) {
    // Pattern.compile and Pattern.matches are static, so the scope is easy to identify.
    // This assumes, of course, that the user never names a variable 'Pattern' or defines
    // their own class with this name. Probably a safe assumption?
    if (isScopedMethodCall(expr)) {
      String scopeName = expr.getScope().get().toString();
      return scopeName.equals("Pattern") || scopeName.equals("java.util.regex.Pattern");
    }
    return false;
  }

  private static boolean isCallTo(MethodCallExpr expr, String method) {
    return expr.getName().asString().equals(method);
  }

  private static boolean isCallToMatches(MethodCallExpr expr) {
    return expr.getName().asString().equals("matches");
  }

  private static void instrumentRegexes(String fileName, String outputFile) throws IOException {
    File file = new File(fileName);

    TypeSolver reflectionTypeSolver = new ReflectionTypeSolver();
    reflectionTypeSolver.setParent(reflectionTypeSolver);
    CombinedTypeSolver combinedSolver = new CombinedTypeSolver();
    combinedSolver.add(reflectionTypeSolver);

    JavaSymbolSolver symbolSolver = new JavaSymbolSolver(combinedSolver);
    JavaParser.getStaticConfiguration().setSymbolResolver(symbolSolver);

    CompilationUnit compilationUnit = JavaParser.parse(file);
     new ModifierVisitor<Void>() {
       @Override
       public MethodCallExpr visit(MethodCallExpr expr, Void arg) {
         super.visit(expr, arg);

         boolean callDefinesARegex = false;
         String pattern = null;
         Expression patternNode = null;
         NodeList<Expression> args = expr.getArguments();
         if (isMethodCallInStringScope(expr)) {
           if (isCallTo(expr, "matches")
               || isCallTo(expr, "split")
               || isCallTo(expr, "replaceFirst")
               || isCallTo(expr, "replaceAll"))
           {
             // Each of these has a regex as the first arg
             if (args.size() >= 1) {
               callDefinesARegex = true;
               patternNode = args.get(0);
             }
           }
         } else if (isMethodCallInPatternScope(expr)) {
           if (isCallTo(expr, "compile")) {
             if (args.size() == 1 || args.size() == 2) {
               // Pattern.compile: Pattern.compile(String pattern[, int flags])
               callDefinesARegex = true;
               patternNode = args.get(0);
               // TODO We could retrieve flags if we wanted, for args.size() > 1.
             }
           } else if (isCallToMatches(expr)) {
             if (args.size() == 2) {
               // Pattern.matches(String pattern, String input)
               callDefinesARegex = true;
               patternNode = args.get(0);
             }
           }
         }

         if (callDefinesARegex) {
           // Replace expr node in AST
           Expression replacement = instrumentTemplate(patternNode, fileName, outputFile);
           args.set(0, replacement);
         }
         return expr;
       }
     }.visit(compilationUnit, null);

      System.out.print(compilationUnit);
  }


  public static Expression instrumentTemplate(Expression strExpr, String sourceFile, String outputFile) {
    // Create a template node. The instrumentation code template is read from a
    // file when this program loads to avoid escaping code as a string literal.
    //
    // The template replaces the original string literal or expression
    // returning a string literal with an anonymous inner class that extends
    // Object with an instrument(String) method that is invoked immediately.
    // The regex is passed to the instrument method, which writes it to a file
    // and then returns it.
    Expression template = JavaParser.parseExpression(codeTemplate);

    // In the template code, replace "REGEXP" with the original AST node,
    // "SOURCEF" with the path of the source file for logging, and OUTPUT_FILE
    // with the log file to collect all regexes when the instrumented code
    // runs.
    template.findAll(StringLiteralExpr.class)
      .stream().forEach(s -> {
        if (s.asString().equals("REGEXP")) {
          s.replace(strExpr);
        } else if (s.asString().equals("SOURCEF")) {
          s.replace(new StringLiteralExpr(sourceFile));
        } else if (s.asString().equals("OUTPUT_FILE")) {
          s.replace(new StringLiteralExpr(outputFile));
        }
      });
    return template;
  }

  /**
   * Convert pattern to a "raw string".
   * This matches how most other languages declare regexes.
   */
  public static String unescapePattern(String pattern) {
    // Java really really needs raw strings! This replaces '\\' with '\'
    String replacement = pattern.replaceAll(Matcher.quoteReplacement("\\\\"), Matcher.quoteReplacement("\\"));
    return replacement;
  }

  /**
    * Load the instrumentation template from a file
    */
  static String loadTemplateFile() throws IOException {
    // Load file from src/main/resources
    InputStream stream = RegexInstrumentor.class.getResourceAsStream("/instrumentationtemplate.txt");
    BufferedReader br = new BufferedReader(new InputStreamReader(stream));
    String template = "";
    String line;
    while ((line = br.readLine()) != null) {
      template += line;
    }
    return template;
  }


  public static void main(String[] args) {
    System.err.println("Begins!");
    if (args.length == 2) {
      String fileName = args[0];
      String outputFile = args[1];

      // System.err.println("Args:");
      // System.err.println("  fileName " + fileName);
      // System.err.println("  outputFile" + outputFile);

      int rc = 0;
      try {
        codeTemplate = loadTemplateFile();
        // System.err.println("Template:\n" + codeTemplate);
        instrumentRegexes(fileName, outputFile);
        rc = 0;
      } catch (Exception e) {
        System.err.println("main: Exception: " + e);
        e.printStackTrace(System.err);
        rc = 1;
      }
      System.exit(rc);
    } else {
      System.out.println("Usage: INVOCATION source-to-instrument.java regex-log-file");
      System.exit(-1);
    }
  }
}
